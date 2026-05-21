import json
from jinja2 import pass_eval_context
from markupsafe import Markup

@pass_eval_context
def pretty_json(eval_ctx, value, indent=2):
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    dumped = json.dumps(value, ensure_ascii=False, indent=indent)
    if eval_ctx.autoescape:
        dumped = Markup(dumped)
    return dumped
