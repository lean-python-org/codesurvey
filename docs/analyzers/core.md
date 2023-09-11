The purpose of an `Analyzer` is to find units of source-code
(typically source-code files) within a `Repo` provided by a
[`Source`](../sources/core.md). An `Analyzer` is configured with one
or more [`FeatureFinders`](features.md) for identifying occurrences of
features of interest within a unit of source-code.

This document provides details of the core `Analyzer` classes that can
be used to define custom `Analyzer` types, while usage of built-in
language-specific Analyzers is documented in the following sub-pages:

* [Python](python.md)

## Custom File Analyzers

You can define your own Analyzer to analyze languages not supported by
the built-in Analyzers, or to use different approaches to parse or
interpret source-code.

Most Analyzers will treat each source-code file within a Repo as the
unit of source-code. Such Analyzers should inherit from
[`FileAnalyzer`][codesurvey.analyzers.Analyzer] and implement a
[`prepare_file()`][codesurvey.analyzers.FileAnalyzer.prepare_file]
method that receives a [`FileInfo`][codesurvey.analyzers.FileInfo] and
returns an appropriate code representation. The code representation
could be a simple string of source-code, or a parsed structure like an
abstract syntax tree (AST) - the type should be specified as a type
argument when inheriting from `FileAnalyzer` (e.g. `class
CustomAnalyzer(FileAnalyzer[str])`).

Your Analyzer should specify a
[`default_file_glob`][codesurvey.analyzers.FileAnalyzer.default_file_glob]
attribute to find source-code files of interest, and may define a set
of
[`default_file_filters`][codesurvey.analyzers.FileAnalyzer.default_file_filters]
to exclude certain files.

Your Analyzer should also specify a `default_name` class attribute
that will be used to identify your Analyzer in logs and results
(except where a name is provided for a specific Analyzer instance).

For example, to define a custom Analyzer that receives a `custom_arg`,
looks for `.py` files, excludes filenames beginning with an
underscore, and represents source-code files for FeatureFinders as
strings:

```python
def leading_underscore_file_filter(file_info):
    return os.path.basename(file_info.rel_path).startswith('_')

class CustomAnalyzer(FileAnalyzer[str]):
    default_name = 'custom'
    default_file_glob = '**/*.py'
    default_file_filters = [
        leading_underscore_file_filter,
    ]

    def __init__(self, custom_arg, *,
                 feature_finders: Sequence[FeatureFinder], *,
                 file_glob: Optional[str] = None,
                 file_filters: Optional[Sequence[Callable[[FileInfo], bool]]] = None,
                 name: Optional[str] = None):
        self.custom_arg = custom_arg
        super().__init__(
            feature_finders=feature_finders,
            file_glob=file_glob,
            file_filters=file_filters,
            name=name,
        )

    def prepare_file(self, file_info: FileInfo) -> str:
        with open(file_info.abs_path) as code_file:
            return code_file.read()
```


When defining a custom Analyzer, you will also need to implement
custom [FeatureFinders](features.md) that expect to receive the type
of code representation you specify for your Analyzer.

### File Analyzer Classes

::: codesurvey.analyzers.FileAnalyzer
    options:
        members: ['default_file_glob', 'default_file_filters', '__init__', 'prepare_file', 'test']

::: codesurvey.analyzers.FileInfo

## Other Custom Analyzers

For Analyzers that don't treat each file as a unit of source-code, you
can define an Analyzer that inherits from
[`Analyzer`][codesurvey.analyzers.Analyzer] and defines
[`prepare_code_representation()`][codesurvey.analyzers.Analyzer.prepare_code_representation]
and
[`code_generator()`][codesurvey.analyzers.Analyzer.code_generator].
[`prepare_code_representation()`][codesurvey.analyzers.Analyzer.prepare_code_representation]
returns a representation (such as a simple string, or a parsed
structure like an abstract syntax tree) for a specific unit of
source-code, while
[`code_generator()`][codesurvey.analyzers.Analyzer.code_generator]
returns [Code][codesurvey.analyzers.Code] results of analyzing each unit
of source-code, or [CodeThunks][codesurvey.analyzers.CodeThunk] that
can be executed in a parallelizable sub-process in order to analyze a
unit of source-code.

### Core Classes

::: codesurvey.analyzers.Analyzer

::: codesurvey.analyzers.Code

::: codesurvey.analyzers.CodeThunk
