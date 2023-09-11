"""Base classes and built-in Sources of code Repos to analyze."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import partial
import os
import os.path
from random import Random
import subprocess
from tempfile import mkdtemp, TemporaryDirectory
from typing import Any, Callable, Dict, Iterator, Mapping, Optional, Sequence, Union

import requests

from codesurvey.utils import logger, noop


class SourceError(Exception):
    """Raised for any failure of a Source to provide a Repo."""
    pass


@dataclass(frozen=True)
class Repo:
    """A repository of code that is accessible in a local directory in
    order to be analyzed."""

    source: 'Source'
    """Source the Repo is provided by."""

    key: str
    """Unique key of the Repo within its Source."""

    # TODO: Change to a pathlib.Path?
    path: str
    """Path to the local directory storing the Repo."""

    cleanup: Callable[[], None] = noop
    """Function to be called to remove or otherwise cleanup the Repo when
    analysis of it has finished."""

    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)
    """Additional properties describing the Repo.

    The metadata structure may vary depending on the type of
    Source.

    """

    def __str__(self):
        return f'{self.source.name}:{self.key}'

    def __repr__(self):
        return f'{self.__class__.__name__}({self})'


@dataclass(frozen=True)
class RepoThunk:
    """An executable task to be run asynchronously to prepare a Repo."""

    source: 'Source'
    """Source the Repo is provided by."""

    key: str
    """Unique key of the Repo within its Source."""

    thunk: Callable[[], Repo]
    """Function to be called to prepare and return the Repo."""

    def __str__(self):
        return f'{self.source.name}:{self.key}'

    def __repr__(self):
        return f'{self.__class__.__name__}({self})'


class Source(ABC):
    """Provides Repos to be anaylyzed by CodeSurvey."""

    default_name: str
    """Default name to be assigned to Sources of this type if a custom
    name is not specified."""

    def __init__(self, *, name: Optional[str] = None):
        """
        Args:
            name: Name to identify the Source. If `None`, defaults to the
                Source type's default_name
        """
        self.name = self.default_name if name is None else name
        if self.name is None:
            raise ValueError('Analyzer name cannot be None')

    @abstractmethod
    def fetch_repo(self, repo_key: str) -> Repo:
        """Prepares the [Repo][codesurvey.sources.Repo] with the given
        `repo_key` for analysis.

        Typically called internally by repo_generator or by a
        RepoThunk, but also useful for inspecting a Repo given it's
        key from a survey result.

        """

    @abstractmethod
    def repo_generator(self) -> Iterator[Union[Repo, RepoThunk]]:
        """Generator yielding [Repos][codesurvey.sources.Repo] ready for
        analysis or [RepoThunks][codesurvey.sources.RepoThunk] that
        can be executed to prepare them for analysis."""

    def __str__(self):
        return self.name

    def __repr__(self):
        return f'{self.__class__.__name__}({self})'

    def repo(self, **kwargs):
        """Internal helper to generate a Repo for this Source. Takes the same
        arguments as Repo except for source."""
        return Repo(source=self, **kwargs)

    def repo_thunk(self, **kwargs):
        """Internal helper to generate a RepoThunk for this Source. Takes the
        same arguments as RepoThunk except for source."""
        return RepoThunk(source=self, **kwargs)


class LocalSource(Source):
    """
    Source of Repos from local filesystem directories.

    Example usage:

    ```python
    LocalSource([
        'path/to/my-source-code-directory',
    ])
    ```

    """
    default_name = 'local'

    def __init__(self, dirs: Sequence[str], *, name: Optional[str] = None):
        """
        Args:
            dirs: Paths to the local source code directory of each Repo
            name: Name to identify the Source. If `None`, defaults to 'local'.
        """
        self.dirs = dirs
        super().__init__(name=name)

    def fetch_repo(self, repo_key: str) -> Repo:
        return self.repo(
            key=repo_key,
            path=repo_key,
        )

    def repo_generator(self) -> Iterator[Repo]:
        for repo_dir in self.dirs:
            yield self.fetch_repo(repo_dir)


def fetch_git_repo(clone_url: str) -> str:
    """Helper function to clone a Git repository from the given URL."""
    temp_dir = mkdtemp()
    try:
        # Perform a shallow clone to reduce the download size.
        subprocess.run(['git', 'clone', '--depth', '1', clone_url, temp_dir],
                       capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as ex:
        raise SourceError((f'Failed to Git clone "{clone_url}" '
                           f'with error code {ex.returncode}\n'
                           f'> STDOUT {ex.stdout}\n'
                           f'> STDERR {ex.stderr}\n'))
    return temp_dir


class GitSource(Source):
    """
    Source of Repos from remote Git repositories.

    Repos are downloaded into a local directory for analysis.

    Example usage:

    ```python
    GitSource([
        'https://github.com/whenofpython/codesurvey',
    ])
    ```

    """
    default_name = 'git'

    def __init__(self, repo_urls: Sequence[str], *, name: Optional[str] = None):
        """
        Args:
            repo_urls: URLs of remote Git repositories.
            name: Name to identify the Source. If `None`, defaults to 'git'.
        """
        self.repo_urls = repo_urls
        super().__init__(name=name)

    def fetch_repo(self, repo_key: str) -> Repo:
        try:
            temp_dir = fetch_git_repo(repo_key)
        except SourceError as ex:
            raise SourceError(f'Source {self} failed to clone from GitHub: {ex}')
        return self.repo(
            key=repo_key,
            path=temp_dir,
            # When the repo is finished being used, the temp_dir
            # should be deleted:
            cleanup=partial(TemporaryDirectory._rmtree, temp_dir),  # type: ignore[attr-defined]
        )

    def repo_generator(self) -> Iterator[RepoThunk]:
        for repo_url in self.repo_urls:
            yield self.repo_thunk(
                key=repo_url,
                thunk=partial(self.fetch_repo, repo_url),
            )


class GithubSampleSource(Source):
    """Source of Repos sampled from GitHub's search API.

    Repos are sampled from randomly selected pages of GitHub search
    results, and downloaded to a temporary directory for analysis.

    For explanations of GitHub search parameters, see:
    https://docs.github.com/en/free-pro-team@latest/rest/search/search#search-repositories

    GitHub authentication credentials can be provided to increase rate
    limits. See:
    https://docs.github.com/en/rest/overview/authenticating-to-the-rest-api

    Example usage:

    ```python
    GithubSampleSource(language='python')
    ```

    """
    default_name = 'github_sample'

    REPOS_PER_PAGE = 100
    # GitHub only returns the first 1,000 search results
    MAX_RESULTS = 1000

    def __init__(self, *,
                 search_query: str = '',
                 language: Optional[str],
                 max_kb: Optional[int] = 50_000,
                 sort: str = 'updated',
                 auth_username: Optional[str] = None,
                 auth_token: Optional[str] = None,
                 random_seed: Optional[int] = None,
                 name: Optional[str] = None):
        """
        Args:
            search_query: An optional search query for GitHub search.
            language: An optional constraint for GitHub's repository
                language tag.
            max_kb: To avoid downloading excessively large repositories,
                limits the maximum kilobyte size of sampled Repos.
            sort: Sort order for GitHub search. Important as GitHub will
                only return the first 1000 pages of search results to sample
                from. Defaults to searching for recently updated repositories.
            auth_username: Username for GitHub authentication.
            auth_token: Token for GitHub authentication.
            random_seed: Random seed for sampling pages of search results.
                If `None`, a randomly selected seed is used.
            name: Name to identify the Source. If `None`, defaults
                to 'github_sample'.
        """
        self.search_query = search_query
        self.language = language
        self.max_kb = max_kb
        self.sort = sort
        self.auth = (auth_username, auth_token) if auth_username and auth_token else None
        self.random_seed = random_seed
        super().__init__(name=name)

    def _search_repos(self, *, page: int = 1) -> dict:
        """
        Makes a GitHub repo search API call for the specified page index.

        Returns a dictionary containing result metadata (total number of pages)
        and a list of dictionaries containing metadata for found repos.

        See:

        * https://docs.github.com/en/rest/search#search-repositories
        * https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
        """
        q_parts = []
        if self.search_query:
            q_parts.append(self.search_query)
        if self.language is not None:
            q_parts.append(f'language:{self.language}')
        if self.max_kb is not None:
            q_parts.append(f'size:<={self.max_kb}')

        params: Dict[str, Union[str, int]] = {
            'q': ' '.join(q_parts),
            'sort': self.sort,
            'per_page': self.REPOS_PER_PAGE,
            'page': page,
        }

        r = requests.get(
            'https://api.github.com/search/repositories',
            auth=self.auth,
            params=params,
        )
        r_json = r.json()
        return {
            # Return the total number of result pages that can be
            # sampled from.
            'page_count': max(self.MAX_RESULTS, r_json['total_count']) / self.REPOS_PER_PAGE,
            # Restrict the list of returned repos to those that
            # have the (optionally) specified language.
            'repos': [
                item for item in r_json['items']
                if (self.language is None or (str(item['language']).lower() == self.language))
            ],
        }

    def _clone_repo(self, repo_data: dict) -> Repo:
        """Helper to clone a Git repository given repo_data from the GitHub repos API."""
        try:
            temp_dir = fetch_git_repo(repo_data['clone_url'])
        except SourceError as ex:
            raise SourceError(f'Source {self} failed to clone from GitHub: {ex}')
        return self.repo(
            key=repo_data['full_name'],
            path=temp_dir,
            # When the repo is finished being used, the temp_dir
            # should be deleted:
            cleanup=partial(TemporaryDirectory._rmtree, temp_dir),  # type: ignore[attr-defined]
            metadata={
                'stars': repo_data['stargazers_count'],
            },
        )

    def fetch_repo(self, repo_key: str) -> Repo:
        r = requests.get(
            'https://api.github.com/repos/{repo_key}',
            auth=self.auth,
        )
        return self._clone_repo(r.json())

    def repo_generator(self) -> Iterator[RepoThunk]:
        rng = Random(self.random_seed)
        page_count = 1
        while True:
            logger.info(f'Source "{self}" searching GitHub for repos')
            search_result = self._search_repos(page=rng.randint(1, page_count))
            page_count = search_result['page_count']
            for repo_data in search_result['repos']:
                yield self.repo_thunk(
                    key=repo_data['full_name'],
                    thunk=partial(self._clone_repo, repo_data),
                )


class TestSource(Source):
    """Creates a single Repo in a temporary directory with specified files
    and contents.

    Only use with trusted paths, as paths are not checked for absolute
    or parent directory navigation.

    """
    default_name = 'test'

    def __init__(self, path_to_content: Mapping[str, str], *, name: Optional[str] = None):
        """
        Args:
            path_to_content: Mapping of paths to contents for files to create
                in a test Repo directory
            name: Name to identify the Source. If `None`, defaults to 'test'.
        """
        self.path_to_content = path_to_content
        super().__init__(name=name)

    def fetch_repo(self, repo_key: str) -> Repo:
        return self.repo(
            key=repo_key,
            path=repo_key,
            # When the repo is finished being used, the temporary
            # directory should be deleted:
            cleanup=partial(TemporaryDirectory._rmtree, repo_key),  # type: ignore[attr-defined]
        )

    def repo_generator(self) -> Iterator[Repo]:
        temp_dir = mkdtemp()
        for path, content in self.path_to_content.items():
            path_head, path_tail = os.path.split(path)
            path_dir = os.path.join(temp_dir, path_head)
            os.makedirs(path_dir, exist_ok=True)
            with open(os.path.join(path_dir, path_tail), 'w') as path_file:
                path_file.write(content)
        yield self.fetch_repo(temp_dir)
