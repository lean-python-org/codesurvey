The purpose of a `Source` is to provide CodeSurvey with repositories
of code (referred to as Repos) to analyze. A `Source` may retrieve
code from specific local directories or remote repositories, or may
use APIs to sample repositories from a large pool, such as from
code-hosting platforms like GitHub.

## Built-In Sources

CodeSurvey provides the following built-in Sources for you to survey
code from common types of code repositories:

::: codesurvey.sources.LocalSource
    options:
        members: ['__init__']

::: codesurvey.sources.GitSource
    options:
        members: ['__init__']

::: codesurvey.sources.GithubSampleSource
    options:
        members: ['__init__']

::: codesurvey.sources.TestSource
    options:
        members: ['__init__']

---


## Custom Sources

You can define your own Source to provide Repos from other storage
providers, platforms or APIs. Simply define a class that inherits from
[`Source`][codesurvey.sources.Source] and defines
[`fetch_repo()`][codesurvey.sources.Source.fetch_repo] and
[`repo_generator()`][codesurvey.sources.Source.repo_generator] methods
that return [Repos][codesurvey.sources.Repo], or
[RepoThunks][codesurvey.sources.RepoThunk] that can be executed in a
parallelizable sub-process in order to prepare a Repo.

Your Source should also specify a `default_name` class attribute that
will be used to identify your Source in logs and results (except where
a name is provided for a specific Source instance).

For example, to define a custom Source that recieves a `custom_arg`
and directly returns [Repos][codesurvey.sources.Repo]:

```python
class CustomSource(Source):
    default_name = 'custom'

    def __init__(self, custom_arg, *, name: Optional[str] = None):
        self.custom_arg = custom_arg
        super().__init__(name=name)

    def fetch_repo(self, repo_key: str) -> Repo:
        repo_path = # TODO
        return self.repo(
            key=repo_key,
            path=repo_path,
        )

    def repo_generator(self) -> Iterator[Repo]:
        while True:
            repo_key = # TODO
            yield self.fetch_repo(repo_key)
```

Alternatively, your custom Source can delay downloading or otherwise
preparing a Repo to a parallelizable sub-process by yielding
[RepoThunks][codesurvey.sources.RepoThunk] from `repo_generator()`:

```python
def repo_generator(self) -> Iterator[RepoThunk]:
    while True:
        repo_key = # TODO
        yield self.repo_thunk(
            key=repo_key,
            thunk=functools.partial(self.fetch_repo, repo_key),
        )
```

### Core Classes

::: codesurvey.sources.Source

::: codesurvey.sources.Repo

::: codesurvey.sources.RepoThunk
