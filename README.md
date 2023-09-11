<div align="center">

<h1>CodeSurvey</h1>

<a href="https://pypi.org/project/codesurvey">
    <img alt="PyPI" src="https://img.shields.io/pypi/v/codesurvey">
</a>

<p>
    <a href="https://github.com/when-of-python/codesurvey">GitHub</a> - <a href="https://when-of-python.github.io/codesurvey">Documentation</a>
</p>

</div>

CodeSurvey is a framework and tool to survey code repositories for
language feature usage, library usage, and more:

* Survey a specific set of repositories, or randomly sample
  repositories from services like GitHub
* Built-in support for analyzing Python code; extensible to support
  any language
* Write simple Python functions to define the code features you want
  to survey; record arbitrary details of feature occurrences
* Supports parallelizization of repository downloading and analysis
  across multiple processes
* Logging and progress tracking to monitor your survey as it runs
* Inspect the results as Python objects, or in an sqlite database


## Installation

```
pip install codesurvey
```


## Usage

The `CodeSurvey` class can easily be configured to run a survey, such
as to measure how often the `math` module is used in a random set of
recently updated Python repositories from GitHub:

```python
from codesurvey import CodeSurvey
from codesurvey.sources import GithubSampleSource
from codesurvey.analyzers.python import PythonAstAnalyzer
from codesurvey.analyzers.python.features import py_module_feature_finder

# Define a FeatureFinder to look for the `math` module in Python code
has_math = py_module_feature_finder('math', modules=['math'])

# Configure the survey
survey = CodeSurvey(
    db_filepath='math_survey.sqlite3',
    sources=[
        GithubSampleSource(language='python'),
    ],
    analyzers=[
        PythonAstAnalyzer(
            feature_finders=[
                has_math,
            ],
        ),
    ],
    max_workers=5,
)

# Run the survey on 10 repositories
survey.run(max_repos=10)

# Report on the results
repo_features = survey.get_repo_features(feature_names=['math'])
repo_count_with_math = sum([
    1 for repo_feature in repo_features if
    repo_feature.occurrence_count > 0
])
print(f'{repo_count_with_math} out of {len(repo_features)} repos use math')
```

![Animated GIF of CodeSurvey demo on the command-line](https://when-of-python.github.io/codesurvey/images/codesurvey-demo.gif)

* For more Sources of repositories, see [Source
  docs](https://when-of-python.github.io/codesurvey/sources/core)
* For more Analyzers and FeatureFinders, see [Analyzer
  docs](https://when-of-python.github.io/codesurvey/analyzers/core)
* For more options and methods for inspecting results, see
  [`CodeSurvey` docs](https://when-of-python.github.io/codesurvey/core)
* For details on directly inspecting the sqlite database of survey
  results see [Database docs](https://when-of-python.github.io/codesurvey/database)
* More examples can be found in
  [examples](https://github.com/when-of-python/codesurvey/tree/main/examples)


## Contributing

* Install Poetry dependencies with `make deps`
* Documentation:
    * Run local server: `make docs-serve`
    * Build docs: `make docs-build`
    * Deploy docs to GitHub Pages: `make docs-github`
    * Docstring style follows the [Google style guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)


## TODO

* Add unit tests
