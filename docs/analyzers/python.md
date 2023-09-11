# Python Analyzers

The `PythonAstAnalyzer` can be used to analyze Python source code
files. An `lxml.etree.Element` representation of each file's abstract
syntax tree (AST) is passed to its `FeatureFinders` for analysis:

::: codesurvey.analyzers.python.PythonAstAnalyzer
    options:
        members: ['default_file_glob', 'default_file_filters', '__init__', 'test']
        inherited_members: ['__init__', 'test']

## Built-In Feature Finders

CodeSurvey comes equipped with the following `FeatureFinders` that can
be used with `PythonAstAnalyzer`:

::: codesurvey.analyzers.python.features.has_for_else
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_try_finally
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_type_hint
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_set_function
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_set_value
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_set
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_fstring
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_ternary
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_pattern_matching
    options:
        show_root_full_path: false
        show_signature: false

::: codesurvey.analyzers.python.features.has_walrus
    options:
        show_root_full_path: false
        show_signature: false

## Custom Python Feature Finders

The following utilities can be used to define simple `FeatureFinders`
that can be used with `PythonAstAnalyzer` to analyze Python abstract
syntax trees:

::: codesurvey.analyzers.python.py_ast_feature_finder

::: codesurvey.analyzers.python.py_ast_feature_finder_with_transform

::: codesurvey.analyzers.python.py_module_feature_finder
