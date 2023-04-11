from mindsdb.integrations.libs.const import HANDLER_TYPE

from mindsdb.integrations.handlers.autosklearn_handler.__about__ import __version__ as version, __description__ as description
try:
    from .huggingface_inference_handler import HuggingFaceInferenceHandler as Handler
    import_error = None
except Exception as e:
    Handler = None
    import_error = e

title = 'Hugging Face Inference API'
name = 'huggingface_iference_api'
type = HANDLER_TYPE.ML
permanent = True

__all__ = [
    'Handler', 'version', 'name', 'type', 'title', 'description', 'import_error'
]
