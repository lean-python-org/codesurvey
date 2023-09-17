"""Library for surveying source code for the frequency of various features.

Typical usage:

```python
from codesurvey import CodeSurvey, LocalSource
from codesurvey.sources import LocalSource
from codesurvey.analyzers.python import PythonAstAnalyzer
from codesurvey.analyzers.python.features import has_set

survey = CodeSurvey(
    sources=[LocalSource(['/path/to/some_python_code'])],
    analyzers=[PythonAstAnalyzer(feature_finders=[has_set])],
)
survey.run(max_repos=1)
print(survey.get_repo_features())
print(survey.get_code_features())
print(survey.get_survey_tree())
```

"""

__version__ = '0.1.1'

from .core import CodeSurvey
from .database import RepoFeature, CodeFeature
from .utils import logger
from . import sources
from . import analyzers

__all__ = [
    'CodeSurvey',
    'RepoFeature',
    'CodeFeature',
    'logger',
    'sources',
    'analyzers',
]
