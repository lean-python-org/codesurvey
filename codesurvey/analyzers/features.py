from dataclasses import dataclass, field
from functools import wraps
from typing import cast, Any, Callable, Dict, Generic, Mapping, Protocol, Sequence, TypeVar, Union


@dataclass
class Feature:
    """Analysis result of a single feature for a single source-code unit."""

    name: str
    """Name of the feature analyzed."""

    occurrences: Sequence[Dict[str, Any]] = field(default_factory=list)
    """Occurrences of the feature within the source-code unit.

    The data captured for each occurrence is determined by the
    [`FeatureFinder`][codesurvey.analyzers.FeatureFinder] that
    produced the Feature.

    """

    ignore: bool = False
    """If `True`, analysis of the feature was skipped for the source-code unit."""


FeatureDict = Dict[str, Any]


CodeReprT = TypeVar('CodeReprT')
# Need a separate contravariant type variable for the protocol below.
CodeReprInputT = TypeVar('CodeReprInputT', contravariant=True)


class FeatureFinder(Protocol, Generic[CodeReprInputT]):
    """Callable for producing a [`Feature`][codesurvey.analyzers.Feature]
    analysis for a given source-code unit representation."""

    name: str
    """Name of the feature that is analyzed."""

    def __call__(self, code_repr: CodeReprInputT) -> Feature:
        """Analyze the given source-code unit representation."""
        pass


def _normalize_feature(*, name: str, feature: Union[Feature, FeatureDict]) -> Feature:
    """Helper for producing a named Feature result from a given Feature or
    FeatureDict.

    Used to allow user-defined feature finders to return either a
    Feature object or equivalent dictionary.

    Args:
        name: Name of the feature
        feature: Feature or dictionary with equivalent data.

    """
    if isinstance(feature, Feature):
        feature.name = name
        return feature
    elif isinstance(feature, Mapping):
        return Feature(name=name, **feature)
    else:
        raise ValueError(('Feature finders must either return a Feature object '
                          'or a dictionary with which to create a Feature. '
                          f'Received: {feature}'))


FeatureFinderFunction = Callable[[CodeReprT], Union[Feature, FeatureDict]]


def feature_finder(name: str) -> Callable[[FeatureFinderFunction[CodeReprT]], FeatureFinder[CodeReprT]]:
    """Decorator for defining a named `FeatureFinder`.

    Example usage:

    ```python
    @feature_finder('while')
    def has_while(code_representation):
        if code_representation is None:
            return {'ignore': True}
        return {
            'occurrences': [
                {'character_index': match.start()}
                for match in re.finditer('test', str(code_representation))
            ]
        }
    ```

    """

    def decorator(func: FeatureFinderFunction[CodeReprT]) -> FeatureFinder[CodeReprT]:

        @wraps(func)
        def decorated(*args, **kwargs):
            feature = func(*args, **kwargs)
            return _normalize_feature(name=name, feature=feature)

        wrapped_feature_finder = cast(FeatureFinder[CodeReprT], decorated)
        wrapped_feature_finder.name = name
        return wrapped_feature_finder

    return decorator


class PartialFeatureFinder(Generic[CodeReprT]):

    def __init__(self, name: str, feature_finder_function: FeatureFinderFunction[CodeReprT], args: Sequence, kwargs: Mapping):
        self.name = name
        self.feature_finder_function = feature_finder_function
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        keywords = {**self.kwargs, **kwargs}
        feature = self.feature_finder_function(*self.args, *args, **keywords)
        return _normalize_feature(name=self.name, feature=feature)


# Create a constructor function for PartialFeatureFinder for cleaner
# interface documentation. A class must be used to produce pickle-able
# partial objects.
def partial_feature_finder(name: str,
                           feature_finder_function: Callable[..., Union[Feature, FeatureDict]],
                           *args, **kwargs) -> FeatureFinder[CodeReprT]:
    """Defines a FeatureFinder from the partial application of the given
    `feature_finder_function` with the given args and kwargs.

    Example usage:

    ```python
    has_math_module = partial_feature_finder('math_module', module_feature_finder, module='math')
    ```

    """
    return PartialFeatureFinder(
        name=name,
        feature_finder_function=feature_finder_function,
        args=args,
        kwargs=kwargs,
    )


def _union_feature_finder(*args, feature_finders: Sequence[FeatureFinder], **kwargs) -> FeatureDict:
    feature_results = [finder(*args, **kwargs) for finder in feature_finders]
    return dict(
        ignore=all([result.ignore for result in feature_results]),
        occurrences=[
            occurrence
            for result in feature_results
            for occurrence in result.occurrences
        ]
    )


def union_feature_finder(name: str, feature_finders: Sequence[FeatureFinder[CodeReprT]]) -> FeatureFinder[CodeReprT]:
    """Defines a FeatureFinder that returns the union of the occurrences
    of the given `feature_finders`.

    The feature will only return an `'ignore'` result if all
    `feature_finders` ignore the given source-code unit.

    Example usage:

    ```python
    has_loop = union_feature_finder('loop', [has_for_loop, has_while_loop])
    ```

    """
    return partial_feature_finder(name, _union_feature_finder, feature_finders=feature_finders)
