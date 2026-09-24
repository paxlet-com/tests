"""Opt-in response envelopes and diagnostics; never log provider exception text."""
import ast
import hashlib
import json
import os
from pathlib import Path
import time

from nl_dsl_sh import LiteLLMClient, Plan
from pydantic import ValidationError

TOKEN_FIELDS = ('prompt_tokens', 'completion_tokens', 'total_tokens')


class RepeatedResponse(ValueError):
    """A repair made no progress; stop before another provider call."""


def unwrap_response(raw, *, allow_fence=False):
    if not allow_fence:
        return raw
    lines = raw.strip().splitlines(keepends=True)
    if not lines or not lines[0].lstrip().startswith('```'):
        return raw
    if (len(lines) < 3 or lines[0].strip() not in ('```json', '```')
            or lines[-1].strip() != '```'
            or any(line.lstrip().startswith('```') for line in lines[1:-1])):
        raise ValueError('INVALID_RESPONSE_ENVELOPE')
    return ''.join(lines[1:-1])


def field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def diagnostic(raw):
    result = {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and 'clarification' in data:
            return {'validation': 'clarification'}
        plan = Plan.model_validate(data)
    except json.JSONDecodeError as error:
        return {'validation': 'invalid-json', 'line': error.lineno, 'column': error.colno}
    except ValidationError as error:
        return {'validation': 'invalid-plan-schema', 'schema_errors': [
            {'type': item['type'], 'location': [str(x)[:80] for x in item['loc']]}
            for item in error.errors(include_input=False, include_context=False, include_url=False)][:10]}
    result['validation'] = 'schema-valid'
    result['syntax'] = []
    for step in plan.steps:
        if step.kind != 'generate' or step.language != 'python':
            continue
        code = step.code
        item = {'step': step.id, 'code_sha256': hashlib.sha256(code.encode()).hexdigest(),
                'newline_count': code.count('\n'), 'literal_backslash_n_count': code.count('\\n')}
        try:
            ast.parse(code)
            item['status'] = 'passed'
        except SyntaxError as error:
            item.update(status='failed', line=error.lineno, column=error.offset, reason=error.msg[:160])
        result['syntax'].append(item)
    return result


class ObservedClient(LiteLLMClient):
    def __init__(self, config, completion, *, artifacts=None, max_calls=1, allow_fence=False):
        if not 1 <= max_calls <= 3:
            raise ValueError('max_calls must be 1..3')
        self.attempts = []
        self.seen = set()
        self.artifacts = Path(artifacts) if artifacts else None
        self.max_calls = max_calls
        self.allow_fence = allow_fence
        if self.artifacts:
            self.artifacts.mkdir(parents=True, exist_ok=False, mode=0o700)
        def measured(**kwargs):
            response = completion(**kwargs)
            usage = field(response, 'usage')
            self.attempts[-1]['usage'] = {key: value if type(value) is int and value >= 0 else None
                                        for key in TOKEN_FIELDS for value in [field(usage, key)]}
            choices = field(response, 'choices')
            self.attempts[-1]['finish_reason'] = field(choices[0], 'finish_reason')
            return response
        super().__init__(config, completion=measured)

    def complete(self, messages):
        if len(self.attempts) >= self.max_calls:
            raise ValueError('MODEL_CALL_BUDGET_EXHAUSTED')
        attempt = {'number': len(self.attempts) + 1, 'usage': {key: None for key in TOKEN_FIELDS}}
        self.attempts.append(attempt)
        started = time.perf_counter()
        try:
            raw = super().complete(messages)
            attempt.update(response_sha256=hashlib.sha256(raw.encode()).hexdigest(), response_bytes=len(raw.encode()))
            if self.artifacts:
                path = self.artifacts / f'response-{attempt["number"]}.txt'
                with open(path, 'x', encoding='utf-8', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
                    stream.write(raw)
                attempt['artifact'] = path.name
            if len(raw) > 1_000_000:
                raise ValueError('MODEL_RESPONSE_TOO_LARGE')
            normalized = unwrap_response(raw, allow_fence=self.allow_fence)
            digest = hashlib.sha256(normalized.encode()).hexdigest()
            attempt.update(normalized_sha256=digest, envelope_removed=normalized != raw, **diagnostic(normalized))
            attempt['repeated_response'] = digest in self.seen
            if digest in self.seen:
                raise RepeatedResponse('REPEATED_MODEL_RESPONSE')
            self.seen.add(digest)
            return normalized
        except Exception as error:
            attempt['error_type'] = type(error).__name__
            raise
        finally:
            attempt['elapsed_ms'] = (time.perf_counter() - started) * 1000

    def usage_summary(self):
        return {'known_tokens': {key: sum(row['usage'][key] or 0 for row in self.attempts) for key in TOKEN_FIELDS},
                'complete': bool(self.attempts) and all(row['usage'][key] is not None for row in self.attempts for key in TOKEN_FIELDS),
                'attempts_missing_usage': [row['number'] for row in self.attempts if any(row['usage'][key] is None for key in TOKEN_FIELDS)]}
