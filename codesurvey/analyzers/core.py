"""Base classes for Analyzers of code in Repos."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partial
from glob import iglob
import os.path
from typing import Callable, Dict, Generic, Iterator, Optional, Sequence, Union

from codesurvey.utils import get_duplicates
from codesurvey.sources import Repo, TestSource
from .features import CodeReprT, FeatureFinder, Feature


@dataclass(frozen=True)
class Code:
    """Results of analyzing a single unit of source-code from a Repo (e.g.
    a file of source-code) for occurrences of target features."""

    analyzer: 'Analyzer'
    """The Analyzer that performed the analysis."""

    repo: Repo
    """The Repo that the Code belongs to."""

    key: str
    """The unique key of the Code within its Repo."""

    features: Dict[str, Feature]
    """A mapping of feature names to Feature survey results."""


@dataclass(frozen=True)
class CodeThunk:
    """An executable task to be run asynchronously to produce a Code
    analysis."""

    analyzer: 'Analyzer'
    """The Analyzer that will perform the analysis."""

    repo: Repo
    """The Repo that the Code belongs to."""

    key: str
    """The unique key of the Code within its Repo."""

    features: Sequence[str]
    """The names of features to be analyzed."""

    thunk: Callable[[], Code]
    """Function to be called to perform the analysis."""


class Analyzer(ABC, Generic[CodeReprT]):
    """Analyzes Repos to produce Code feature analysis results of
    individual units of source-code (such as source-code files).

    The type argument is the representation of source-code units that
    will be provided to FeatureFinders used with Analyzer instances.

    """

    default_name: str
    """Name to be assigned to Analyzers of this type if a custom name is not
    specified."""

    def __init__(self, *, feature_finders: Sequence[FeatureFinder[CodeReprT]],
                 name: Optional[str] = None):
        """
        Args:
            feature_finders:
                The [FeatureFinders][codesurvey.analyzers.FeatureFinder]
                for analyzing each source-code unit.
            name: Name to identify the Analyzer. If `None`, defaults to the
                Analyzer type's default_name
        """
        self.name = self.default_name if name is None else name
        duplicate_feature_names = get_duplicates([feature.name for feature in feature_finders])
        if duplicate_feature_names:
            duplicate_features_str = ', '.join(duplicate_feature_names)
            raise ValueError((f'Cannot instantiate analyzer "{self}" with duplicate '
                              f'feature names: {duplicate_features_str}. '
                              'Please set a unique name for each feature_finder.'))
        self.feature_finders = {feature.name: feature for feature in feature_finders}

    @abstractmethod
    def prepare_code_representation(self, repo: Repo, code_key: str) -> CodeReprT:
        """Returns a representation of a source-code unit that can be passed
        to the [FeatureFinders][codesurvey.analyzers.FeatureFinder] of
        this Analyzer.

        Args:
            repo: Repo containing the source-code to be analyzed.
            code_key: Unique key of the source-code unit to be analyzed
                within the Repo.

        """

    @abstractmethod
    def code_generator(self, repo: Repo, *,
                       get_code_features: Callable[[str], Sequence[str]]) -> Iterator[Union[Code, CodeThunk]]:
        """Generator yielding [Codes][codesurvey.analyzers.Code] analysis
        results of source-code units within the given Repo, or
        [CodeThunks][codesurvey.analyzers.CodeThunk] that can be
        executed to perform such analyses.

        Args:
            repo: Repo containing the source-code to be analyzed.
            get_code_features: A function that will be called by
                `code_generator()` with a Code's key to get the subset of
                [`get_feature_names()`][codesurvey.analyzers.Analyzer.get_feature_names]
                that should be analyzed for that Code.

        """

    def __str__(self):
        return self.name

    def __repr__(self):
        return f'{self.__class__.__name__}({self})'

    def analyze_code(self, repo: Repo, code_key: str, features: Sequence[str]) -> Code:
        """Produces a [Code][codesurvey.analyzers.Code] analysis for a single
        unit of source-code within a Repo.

        Args:
            repo: Repo containing the source-code to be analyzed.
            code_key: Unique key of the source-code unit to be analyzed
                within the Repo.
            features: Names of features to include in the analysis.
                A subset of the names returned by
                [`get_feature_names()`][codesurvey.analyzers.Analyzer.get_feature_names].

        """
        code_repr = self.prepare_code_representation(repo=repo, code_key=code_key)
        if code_repr is None:
            feature_results = {feature_name: Feature(name=feature_name, ignore=True)
                               for feature_name in features}
        else:
            feature_results = {feature_name: self.feature_finders[feature_name](code_repr)
                               for feature_name in features}
        return self.code(
            repo=repo,
            key=code_key,
            features=feature_results,
        )

    def get_feature_names(self) -> Sequence[str]:
        """Returns the names of all features analyzed by this Analyzer instance."""
        return list(self.feature_finders.keys())

    def code(self, **kwargs) -> Code:
        """Internal helper to generate a Code for this Analyzer. Takes the same
        arguments as Code except for analyzer."""
        return Code(analyzer=self, **kwargs)

    def code_thunk(self, **kwargs) -> CodeThunk:
        """Internal helper to generate a CodeThunk for this Analyzer. Takes
        the same arguments as CodeThunk except for analyzer."""
        return CodeThunk(analyzer=self, **kwargs)


@dataclass(frozen=True)
class FileInfo:
    """Details identifying a source-code file within a Repo."""

    repo: Repo
    """Repo that the file belongs to."""

    rel_path: str
    """Relative path to the file from the Repo directory."""

    @property
    def abs_path(self) -> str:
        """Absolute path to the file."""
        return os.path.join(self.repo.path, self.rel_path)


class FileAnalyzer(Analyzer[CodeReprT]):
    """Base class for Analyzers that analyze each source-code file as the
    target unit of code within a Repo.

    The type argument is the representation of source-code units that
    will be provided to FeatureFinders used with Analyzer instances.

    """

    default_file_glob: str
    """Default glob pattern for finding source-code files. To be assigned
    to FileAnalyzers of this type if a custom glob is not specified."""

    default_file_filters: Sequence[Callable[[FileInfo], bool]] = []
    """Default filters to identify files to exclude from analysis. To be
    assigned to FileAnalyzers of this type if custom filters are not
    specified."""

    def __init__(self, feature_finders: Sequence[FeatureFinder], *,
                 file_glob: Optional[str] = None,
                 file_filters: Optional[Sequence[Callable[[FileInfo], bool]]] = None,
                 name: Optional[str] = None):
        """
        Args:
            feature_finders:
                The [FeatureFinders][codesurvey.analyzers.FeatureFinder]
                for analyzing each source-code file.
            file_glob: Glob pattern for finding source-code files within
                the Repo.
            file_filters: Filters to identify files to exclude from analysis.
                Each filter is a function that takes a
                [`FileInfo`][codesurvey.analyzers.FileInfo] and
                returns `True` if the file should be excluded. file_filters
                cannot be lambdas, as they need to be pickled when passed to
                sub-processes.
            name: Name to identify the Analyzer. If `None`, defaults to the
                Analyzer type's default_name.

        """
        super().__init__(feature_finders=feature_finders, name=name)
        self.file_glob = self.default_file_glob if file_glob is None else file_glob
        self.file_filters = self.default_file_filters if file_filters is None else file_filters

    @abstractmethod
    def prepare_file(self, file_info: FileInfo) -> CodeReprT:
        """Given a [`FileInfo`][codesurvey.analyzers.FileInfo] identifying the
        location of a target source-code file, returns a
        representation of the code that can be passed to the
        [FeatureFinders][codesurvey.analyzers.FeatureFinder] of this
        Analyzer."""

    def prepare_code_representation(self, repo: Repo, code_key: str) -> CodeReprT:
        file_info = FileInfo(repo=repo, rel_path=code_key)
        return self.prepare_file(file_info)

    def _get_file_keys(self, repo: Repo) -> Iterator[str]:
        """Generator yielding the code_keys (relative file paths) within the
        given Repo, applying configured file_filters."""
        for abs_path in iglob(os.path.join(repo.path, self.file_glob), recursive=True):
            if not os.path.isfile(abs_path):
                continue
            file_info = FileInfo(
                repo=repo,
                rel_path=os.path.relpath(abs_path, start=repo.path),
            )
            filtered_out = any([
                file_filter(file_info)
                for file_filter in self.file_filters
            ])
            if filtered_out:
                continue
            yield file_info.rel_path

    def code_generator(self, repo: Repo, *,
                       get_code_features: Callable[[str], Sequence[str]]) -> Iterator[CodeThunk]:
        for file_key in self._get_file_keys(repo):
            features = get_code_features(file_key)
            if len(features) == 0:
                continue

            yield self.code_thunk(
                repo=repo,
                key=file_key,
                features=features,
                thunk=partial(self.analyze_code, repo=repo, code_key=file_key, features=features),
            )

    def test(self, code_snippet: str, *, test_filename: str = 'test_file.txt') -> Dict[str, Feature]:
        """Utility for directly analyzing a string of source-code.

        A Repo will be created in a temporary directory to perform
        analysis of a file created with the given `code_snippet`.

        Args:
            code_snippet: String of source-code to analyze.
            test_filename: Optional custom filename used for the test file.

        Returns:
            A dictionary mapping feature names to
                [`Feature`][codesurvey.analyzers.Feature] results.

        """
        source = TestSource({test_filename: code_snippet})
        repo = next(source.repo_generator())
        code = self.analyze_code(
            repo=repo,
            code_key=test_filename,
            features=self.get_feature_names(),
        )
        return code.features
