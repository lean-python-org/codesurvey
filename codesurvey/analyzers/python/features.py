from functools import wraps
from typing import Callable, Optional, Sequence

import lxml.etree

from codesurvey.analyzers import (
    FeatureDict, FeatureFinder,
    feature_finder, partial_feature_finder, union_feature_finder,
)


ElementTransform = Callable[[lxml.etree.Element], Optional[lxml.etree.Element]]


def get_first_line_number(element: lxml.etree.Element) -> Optional[int]:
    """Returns the earliest line number of an element of any of its descendents."""
    line_no_strs = set(element.xpath('descendant-or-self::*[@lineno]/@lineno'))
    if len(line_no_strs) == 0:
        return None
    return min(map(int, line_no_strs))


def _py_ast_feature_finder(xml: lxml.etree.Element, *, xpath: str,
                           transform: Optional[ElementTransform] = None) -> FeatureDict:
    elements = xml.xpath(f'descendant-or-self::{xpath}')
    if transform is not None:
        elements = [el for el in map(transform, elements) if el is not None]
    return dict(
        occurrences=[
            {'first_line_number': get_first_line_number(el)}
            for el in elements
        ],
    )


def py_ast_feature_finder(name: str, *, xpath: str) -> FeatureFinder[lxml.etree.Element]:
    """Defines a FeatureFinder that looks for elements in a Python AST
    matching the given xpath query.

    To explore the AST structure of the code constructs you are
    interested in identifying, consider using a tool like:
    https://python-ast-explorer.com/

    """
    return partial_feature_finder(name, _py_ast_feature_finder, xpath=xpath)


def py_ast_feature_finder_with_transform(name: str, *, xpath: str) -> Callable[[ElementTransform], FeatureFinder[lxml.etree.Element]]:
    """Decorator for defining a FeatureFinder that looks for elements in a
    Python AST matching the given xpath query, transforming found elements
    with decorated function.

    The function should receive and return an `lxml.etree.Element`, or
    return `None` if the element should not be considered an
    occurrence of the feature.

    Example usage to look for function calls where the function name
    is 'set':

    ```python
    @py_ast_feature_finder_with_transform('set_function', xpath='Call/func/Name')
    def has_set_function(func_name_el):
        if func_name_el.get('id') == 'set':
            return func_name_el
        return None
    ```

    To explore the AST structure of the code constructs you are
    interested in identifying, consider using a tool like:
    https://python-ast-explorer.com/

    """

    def decorator(func: ElementTransform) -> FeatureFinder[lxml.etree.Element]:

        @wraps(func)
        @feature_finder(name)
        def decorated(xml):
            return _py_ast_feature_finder(xml, xpath=xpath, transform=func)

        return decorated

    return decorator


def _py_module_feature_finder(xml: lxml.etree.Element, *, modules: Sequence[str]):
    matched_els = []

    # import syntax
    import_els = xml.xpath('descendant-or-self::Import')
    for import_el in import_els:
        indiv_import_els = import_el.xpath('names/alias')
        for indiv_import_el in indiv_import_els:
            module = indiv_import_el.get('name')
            if module and any([module.startswith(target_module) for target_module in modules]):
                matched_els.append(indiv_import_el)
    # from syntax
    from_els = xml.xpath('descendant-or-self::ImportFrom')
    for from_el in from_els:
        module = from_el.get('module')
        if module and any([module.startswith(target_module) for target_module in modules]):
            matched_els.append(from_el)

    return dict(
        occurrences=[
            {'first_line_number': get_first_line_number(el)}
            for el in matched_els
        ],
    )


def py_module_feature_finder(name: str, *, modules: Sequence[str]) -> FeatureFinder:
    """Defines a FeatureFinder that looks for import statements of one or
    more target Python `modules`.

    Example usage:

    ```python
    has_dataclasses = py_module_feature_finder('dataclasses_module', modules=['dataclasses'])
    ```

    """
    return partial_feature_finder(name, _py_module_feature_finder, modules=modules)


# ==== Python AST Feature Finders ====

# https://docs.python.org/3/library/ast.html#ast.Try
@py_ast_feature_finder_with_transform('for_else', xpath='For/orelse')
def has_for_else(orelse_el):
    """FeatureFinder for else clauses in for loops."""
    if len(orelse_el) == 0:
        return None
    return orelse_el


# https://docs.python.org/3/library/ast.html#ast.Try
@py_ast_feature_finder_with_transform('try_finally', xpath='Try/finalbody')
def has_try_finally(finalbody_el):
    """FeatureFinder for finally clauses in try statements."""
    if len(finalbody_el) == 0:
        return None
    return finalbody_el


# E.g. `def greeting(name: str):`
@py_ast_feature_finder_with_transform('type_hint', xpath='FunctionDef/args/arguments//annotation')
def has_type_hint(annotation_el):
    """FeatureFinder for type hints."""
    if annotation_el.get('*') is not None:
        return annotation_el
    return None


# The set function
@py_ast_feature_finder_with_transform('set_function', xpath='Call/func/Name')
def has_set_function(func_name_el):
    """FeatureFinder for the set function."""
    if func_name_el.get('id') == 'set':
        return func_name_el
    return None


# A set literal
has_set_value = py_ast_feature_finder('set_value', xpath='Set')
"""FeatureFinder for set literals."""

# The set function or literal
has_set = union_feature_finder('set', [has_set_function, has_set_value])
"""FeatureFinder for sets."""

# Node representing a single formatting field in an f-string.
# https://docs.python.org/3/library/ast.html#ast.FormattedValue
has_fstring = py_ast_feature_finder('fstring', xpath='FormattedValue')
"""FeatureFinder for f-strings."""

# E.g. `if b else c`
# https://docs.python.org/3/library/ast.html#ast.IfExp
has_ternary = py_ast_feature_finder('ternary', xpath='IfExp')
"""FeatureFinder for ternary expressions."""

# https://docs.python.org/3/library/ast.html#ast.Match
has_pattern_matching = py_ast_feature_finder('pattern_matching', xpath='Match')
"""FeatureFinder for pattern matching."""

# https://docs.python.org/3/library/ast.html#ast.NamedExpr
has_walrus = py_ast_feature_finder('walrus', xpath='NamedExpr')
"""FeatureFinder for the walrus operator."""
