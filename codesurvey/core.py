"""Top-level components for running and analyzing code surveys."""

import concurrent.futures
from dataclasses import dataclass
from itertools import cycle
import os
import signal
import sys
from typing import cast, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from tqdm.utils import _screen_shape_wrapper

from .utils import logger, BreakException, get_duplicates, recursive_update
from .sources import Repo, RepoThunk, Source
from .analyzers import Code, CodeThunk, Analyzer
from .database import Database, RepoFeature, CodeFeature


@dataclass(frozen=True)
class Job:
    callback: Callable[[concurrent.futures.Future], None]


@dataclass(frozen=True)
class RepoJob(Job):
    source: Source
    analyzer_features: Dict[str, Sequence[str]]


@dataclass(frozen=True)
class CodeJob(Job):
    analyzer: Analyzer
    repo: Repo


class CodeSurveyRunner:
    """Manages the execution of surveys."""

    def __init__(self, survey: 'CodeSurvey'):
        """
        Args:
            survey: The survey that this runner will execute.
        """
        # Survey attributes
        self.survey = survey
        self.sources = survey.sources
        self.analyzers = survey.analyzers
        self.analyzer_features = survey.analyzer_features
        self.max_workers = survey.max_workers
        self.continue_on_failure = survey.continue_on_failure
        self.save_code_features = survey.save_code_features
        self.save_occurrences = survey.save_occurrences
        self.use_saved_features = survey.use_saved_features

    def get_pbars(self, *, disable_progress: bool,
                  progress_analyzer_features: Optional[Mapping[str, Sequence[str]]],
                  ) -> Dict[Union[str, Tuple[str, ...]], tqdm]:
        """Returns progress bars for the processing of Repos and Codes, as
        well as a border above both progress bars.

        Args:
            disable_progress: If True, progress bar objects will be disabled.
            progress_analyzer_features: See [[codesurvey.core.CodeSurvey.run]]

        """
        if progress_analyzer_features is None:
            all_features = [
                feature
                for features in self.analyzer_features
                for feature in features
            ]
            max_auto_feature_progress = 10
            if len(all_features) > max_auto_feature_progress:
                logger.warning((
                    'Disabling progress trackers for features as there are more '
                    f'than {max_auto_feature_progress} features. To prevent this '
                    'warning, set progress_analyzer_features={}'
                ))
                progress_analyzer_features = {}
            else:
                progress_analyzer_features = self.analyzer_features

        cols = 10
        screen_shape = _screen_shape_wrapper()
        if screen_shape:
            cols = screen_shape(sys.stderr)[0] or cols

        bar_format_with_total = '{desc}: {n_fmt}/{total_fmt} [{elapsed}, {rate_fmt}{postfix}]|{bar}| {percentage:3.0f}% [{remaining} remaining]'
        bar_format_without_total = '{desc}: {n_fmt} [{elapsed}, {rate_fmt}{postfix}]'

        border_pbar = tqdm(
            bar_format=('=' * cols),
            disable=disable_progress,
        )
        repo_pbar = tqdm(
            desc='Repos',
            unit='repos',
            total=self.max_repos,
            bar_format=(bar_format_without_total if self.max_repos is None else bar_format_with_total),
            disable=disable_progress,
        )
        code_pbar = tqdm(
            desc='Codes',
            unit='codes',
            total=self.max_codes,
            bar_format=(bar_format_without_total if self.max_codes is None else bar_format_with_total),
            disable=disable_progress,
        )
        feature_pbars: Dict[Union[str, Tuple[str, ...]], tqdm] = {
            ('feature', analyzer_name, feature_name): tqdm(
                desc=f'Repos with {analyzer_name}:{feature_name}',
                unit='repos',
                bar_format='{desc}: {n_fmt}',
                disable=disable_progress,
            )
            for analyzer_name, feature_names in progress_analyzer_features.items()
            for feature_name in feature_names
        }
        return {
            'border': border_pbar,
            'repos': repo_pbar,
            'codes': code_pbar,
            **feature_pbars,
        }

    def handle_failure(self, *, ex: Exception, message: str):
        """Callback to handle exceptions raised in runner subprocesses."""
        # Simplify subprocess error tracebacks by reporting the cause directly.
        if isinstance(ex.__cause__, concurrent.futures.process._RemoteTraceback):
            ex = ex.__cause__

        if self.continue_on_failure:
            logger.error(f'{message}, skipping: {ex}')
        else:
            logger.error(f'{message}')
            # Simplify traceback by clearing the exception chain.
            raise ex from None

    def get_repo_generator(self) -> Iterator[Union[Repo, RepoThunk]]:
        """Returns a generator that draws Repos/RepoThunks from Sources in a
        round-robin fashion."""
        source_repo_generators = {source: source.repo_generator()
                                  for source in self.sources.values()}
        # Round-robin over Sources.
        for source in cycle(self.sources.values()):
            # Finish when all Sources are exhausted
            if len(source_repo_generators) == 0:
                return
            # Skip to the next Source if this one is exhausted
            if source not in source_repo_generators:
                continue
            try:
                yield next(source_repo_generators[source])
            except StopIteration:
                # Remove exhausted Sources
                del source_repo_generators[source]
            except Exception as ex:
                self.handle_failure(
                    ex=ex,
                    message=f'Failed to fetch repo from source "{source}"',
                )

    def get_executor(self) -> concurrent.futures.ProcessPoolExecutor:
        """Returns a multi-processing executor for running repo-fetching and
        code-processing subprocesses."""

        def init_worker():
            # Ignore keyboard interrupts in subprocesses.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

        return concurrent.futures.ProcessPoolExecutor(
            max_workers=self.max_workers,
            initializer=init_worker,
        )

    def reached_max_repos(self) -> bool:
        """Checks whether the number of Repos being fetched, being analyzed,
        and fully analyzed has reached the configured max_repos."""
        if self.max_repos is None:
            return False

        pending_repos = len([job for job in self.future_to_job.values()
                             if isinstance(job, RepoJob)])
        repo_count = len(self.current_repos) + pending_repos + self.completed_repo_count
        return repo_count >= self.max_repos

    def reached_max_codes(self) -> bool:
        """Checks whether the number of analyzed Codes has reached the
        configured max_repos."""
        if self.max_codes is None:
            return False

        return self.completed_code_count >= self.max_codes

    def check_repo_completion(self, repos: Sequence[Repo]) -> None:
        """Check whether there are any completed current_repos without any
        remaining CodeJobs, save their results, and remove them from
        current_repos."""
        completed_repos = [
            repo for repo in self.current_repos
            if len([
                job for job in self.future_to_job.values()
                if isinstance(job, CodeJob) and job.repo is repo
            ]) == 0
        ]
        for repo in completed_repos:
            self.db.save_repo_features(repo, keep_code_features=self.save_code_features)
            self.completed_repo_count += 1
            self.pbars['repos'].update(1)

            repo_features = self.db.get_repo_features(
                source_names=[repo.source.name],
                repo_keys=[repo.key],
            )
            for repo_feature in repo_features:
                if repo_feature.occurrence_count > 0:
                    feature_pbar_key = (
                        'feature',
                        repo_feature.analyzer_name,
                        repo_feature.feature_name,
                    )
                    self.pbars[feature_pbar_key].update(1)

            logger.info(f'Completed repo "{repo}"')
            repo.cleanup()
            self.current_repos.remove(repo)

    def handle_code(self, *, code: Code) -> None:
        """Save survey results for the given Code, updating progress tracking."""
        if self.reached_max_codes():
            return

        self.db.save_code_features(code, save_occurrences=self.save_occurrences)
        self.pbars['codes'].update(1)
        self.completed_code_count += 1

    def handle_code_future(self, future: concurrent.futures.Future) -> None:
        """Handle saving a completed CodeJob, handling Job failure."""
        job = cast(CodeJob, self.future_to_job[future])
        try:
            code = future.result()
        except Exception as ex:
            self.handle_failure(
                ex=ex,
                message=f'Failed to analyze code from repo "{job.repo}" with analyzer "{job.analyzer}"',
            )
        else:
            self.handle_code(code=code)

    def handle_repo(self, *, repo: Repo, analyzer_features: Mapping[str, Sequence[str]]) -> None:
        """Analyze the given Repo for the given analyzer_features.

        All Codes for the Repo will either be analyzed or have a
        pending CodeJob after calling this function.

        """
        # Add the repo to the list of current_repos currently being analyzed.
        self.current_repos.append(repo)
        self.db.save_repo_metadata(repo)
        try:
            if self.reached_max_codes():
                raise BreakException()
            for analyzer in self.analyzers.values():
                features = analyzer_features.get(analyzer.name)
                if features is None:
                    logger.info(f'Skipping completed analyzer "{analyzer}" for repo "{repo}"')
                    continue

                analyzer = self.analyzers[analyzer.name]
                try:
                    logger.info(f'Analyzing repo "{repo}" with analyzer "{analyzer}"')

                    def get_code_features(code_key: str) -> Sequence[str]:
                        """Determine which features still need to be surveyed for the given
                        Code (all features if not use_saved_features)"""
                        if not self.use_saved_features:
                            return cast(Sequence[str], features)
                        return self.db.get_code_missing_features(
                            source_name=repo.source.name,
                            repo_key=repo.key,
                            analyzer_name=analyzer.name,
                            code_key=code_key,
                            features=features,
                        )

                    analyzer_codes = analyzer.code_generator(
                        repo=repo,
                        get_code_features=get_code_features,
                    )
                except Exception as ex:
                    self.handle_failure(
                        ex=ex,
                        message=f'Failed to get analyzer "{analyzer}" codes for repo "{repo}"',
                    )
                else:
                    # Loop over each Code found by the Analyzer
                    for code_or_thunk in analyzer_codes:
                        if self.reached_max_codes():
                            raise BreakException()

                        if isinstance(code_or_thunk, CodeThunk):
                            # If it's a CodeThunk, submit a Job to
                            # analyze the Code, with a callback to
                            # save the results.
                            future = self.executor.submit(cast(Callable, code_or_thunk.thunk))
                            self.future_to_job[future] = CodeJob(
                                analyzer=analyzer,
                                repo=repo,
                                callback=self.handle_code_future,
                            )
                        else:
                            # If it's a Code that is already analyzed,
                            # go straight to saving the results.
                            self.handle_code(code=cast(Code, code_or_thunk))
        except BreakException:
            logger.info(f'Max codes reached, "{repo}" will not be fully analyzed')
        finally:
            self.check_repo_completion([repo])

    def handle_repo_future(self, future: concurrent.futures.Future) -> None:
        """Handle analysis of a completed RepoJob, handling Job failure."""
        job = cast(RepoJob, self.future_to_job[future])
        try:
            repo = future.result()
        except Exception as ex:
            self.handle_failure(
                ex=ex,
                message=f'Failed to fetch repo from source "{job.source}"',
            )
        else:
            self.handle_repo(
                repo=repo,
                analyzer_features=job.analyzer_features,
            )

    def consume_repos(self) -> None:
        """Consume Repos from the repo_generator

        When a Source yields a RepoThunk or an Analyzer yields a
        CodeThunk, it starts a RepoJob/CodeJob and adds it to
        future_to_job - and this function returns when the number of
        pending tasks reaches the number of sub-process workers.

        When a Source yields a Repo or an Analyzer yields a
        Code, they are handled synchronously in this function.

        """
        while (
            # Check for idle workers
            (len(self.future_to_job) < self.max_workers)
            # Check for max_repos and max_codes
            and not self.reached_max_repos()
            and not self.reached_max_codes()
        ):
            # Get the next Repo or RepoThunk from the repo_generator
            try:
                repo_or_thunk = next(self.repo_generator)
            except StopIteration:
                break
            # Determine which Analyzer features still need to be
            # surveyed for the Repo (all features if not
            # use_saved_features)
            repo_analyzer_features = (
                self.db.get_repo_missing_analyzer_features(
                    source_name=repo_or_thunk.source.name,
                    repo_key=repo_or_thunk.key,
                    analyzer_features=self.analyzer_features,
                )
                if self.use_saved_features
                else self.analyzer_features
            )

            # Continue if this is a duplicate of a repo we're already analyzing.
            if any((repo.source.name == repo_or_thunk.source.name)
                   and (repo.key == repo_or_thunk.key)
                   for repo in self.current_repos):
                logger.info(f'Skipping in-progress repo "{repo_or_thunk}"')
                continue

            # Continue if there are no missing features.
            if len(repo_analyzer_features) == 0:
                logger.info(f'Skipping fully analyzed repo "{repo_or_thunk}"')
                continue

            if isinstance(repo_or_thunk, RepoThunk):
                # If it's a RepoThunk, submit a Job to fetch the Repo,
                # with a callback to handle it's analysis later.
                logger.info(f'Fetching repo "{repo_or_thunk}"')
                future = self.executor.submit(cast(Callable, repo_or_thunk.thunk))
                self.future_to_job[future] = RepoJob(
                    source=repo_or_thunk.source,
                    analyzer_features=repo_analyzer_features,
                    callback=self.handle_repo_future,
                )
            else:
                # If it's a Repo that doesn't need to be fetched, go
                # straight to handling the analysis of the Repo.
                self.handle_repo(
                    repo=cast(Repo, repo_or_thunk),
                    analyzer_features=repo_analyzer_features,
                )

    def run(self,
            max_repos: Optional[int] = None,
            max_codes: Optional[int] = None,
            disable_progress: bool = False,
            progress_analyzer_features: Optional[Mapping[str, Sequence[str]]] = None) -> None:
        """Start the runner."""
        # Run configuration
        self.max_repos = max_repos
        self.max_codes = max_codes
        # State initialization
        self.completed_repo_count = 0
        self.completed_code_count = 0
        self.db = self.survey.get_db()
        self.pbars = self.get_pbars(
            disable_progress=disable_progress,
            progress_analyzer_features=progress_analyzer_features,
        )
        self.repo_generator = self.get_repo_generator()
        self.executor = self.get_executor()
        # Keep track of jobs submitted to the executor
        self.future_to_job: Dict[concurrent.futures.Future, Job] = {}
        # Keep track of Repos that are currently being analyzed.
        self.current_repos: List[Repo] = []

        logger.info(f'Preparing database in {self.db.filepath}')
        self.db.initialize()

        with logging_redirect_tqdm(loggers=[logger]):
            try:
                while True:
                    # Start Repo-fetching and Code-analyzing jobs and
                    # add them to future_to_job until all workers are
                    # occupied.
                    self.consume_repos()

                    # If there are no jobs left uncompleted or unprocessed,
                    if len(self.future_to_job) == 0:
                        break

                    # Wait for at least one job to finish.
                    done, _ = concurrent.futures.wait(
                        self.future_to_job,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    # Process each finished job
                    for future in done:
                        job = self.future_to_job[future]
                        job.callback(future)
                    # Remove finished sub-tasks from future_to_job
                    self.future_to_job = {future: self.future_to_job[future]
                                          for future in self.future_to_job
                                          if future not in done}
                    # Finish the processing of any completed
                    # current_repos, removing them from current_repos.
                    self.check_repo_completion(self.current_repos)
            except KeyboardInterrupt:
                logger.info('Interrupted')
                raise
            finally:
                for future in self.future_to_job:
                    future.cancel()
                for process in self.executor._processes.values():
                    process.terminate()
                self.executor.shutdown()
                for repo in self.current_repos:
                    repo.cleanup()
                for pbar in self.pbars.values():
                    pbar.close()
                self.db.close()


class CodeSurvey:
    """Primary interface for running surveys and inspecting their results.

    A CodeSurvey is instantiated with a set of
    [Sources](sources/core.md) to be surveyed and a set of
    [Analyzers](analyzers/core.md) to count the occurrences of
    *features* within them. Each Source may fetch multiple *Repos*
    (e.g. a project directory, a git repository), each of which may
    contain multiple *Codes* (e.g. a source-code file) to be analyzed.
    Each Analyzer will be configured to identify a particular set of
    *features* within each Code.

    Additional arguments can be passed to
    [`__init__()`][codesurvey.CodeSurvey.__init__] to control
    persistent storage, parallelism, and other options.

    The survey can be executed with
    [`run()`][codesurvey.CodeSurvey.run], which accepts options that
    determine the stopping condition for the survey. Multiple calls to
    [`run()`][codesurvey.CodeSurvey.run] will extend the results of
    the survey.

    [`get_repo_features()`][codesurvey.CodeSurvey.get_repo_features],
    [`get_code_features()`][codesurvey.CodeSurvey.get_code_features],
    and [`get_survey_tree()`][codesurvey.CodeSurvey.get_survey_tree]
    can be used to inspect the results of the survey.

    Previous survey results can be loaded for inspection specifying
    the same `db_filepath` used for previous survey run(s).

    """

    def __init__(self, *,
                 sources: Sequence[Source],
                 analyzers: Sequence[Analyzer],
                 db_filepath: str = ':memory:',
                 max_workers: Optional[int] = 1,
                 continue_on_failure: bool = True,
                 save_code_features: bool = True,
                 save_occurrences: bool = True,
                 use_saved_features: bool = True):
        """
        Args:
            sources: Sources from which to fetch Repos of Codes
                to survey. If multiple Sources are provided, Repo fetching
                will cycle through them in a round-robin fashion.
            analyzers: Analyzers to identify features in fetched code.
            db_filepath: Path to an sqlite database file for persisting survey
                results. Creates a new sqlite database if the path does not
                exist. Defaults to a non-persistent in-memory database.
            max_workers: The maximum number of parallel worker processes for
                fetching Repos from Sources and executing Analyzers. Defaults
                to a single worker.
            continue_on_failure: If `True`, exceptions raised by Sources and
                Analyzers will be logged, but will not halt the survey.
            save_code_features: If `True`, features of individual Codes will be
                retained in the survey database. Otherwise, Code features will
                be deleted once they have been used to compute aggregate
                features of its respective Repo.
            save_occurrences: If `True`, occurrence objects returned by
                FeatureFinders will be saved in the survey database.
            use_saved_features: If `True`, re-use saved features from an
                Analyzer for a Code when they already exist in the survey
                database. Otherwise, reapply all Analyzers to all Codes.

        Raises:
            ValueError: Invalid survey configuration was specified.

        """
        duplicate_source_names = get_duplicates([source.name for source in sources])
        if duplicate_source_names:
            duplicate_sources_str = ', '.join(duplicate_source_names)
            raise ValueError(('Cannot instantiate CodeSurvey with duplicate '
                              f'source names: {duplicate_sources_str}. '
                              'Please set a unique name for each source.'))
        self.sources = {source.name: source for source in sources}

        duplicate_analyzer_names = get_duplicates([analyzer.name for analyzer in analyzers])
        if duplicate_analyzer_names:
            duplicate_analyzers_str = ', '.join(duplicate_analyzer_names)
            raise ValueError(('Cannot instantiate CodeSurvey with duplicate '
                              f'analyzer names: {duplicate_analyzers_str}. '
                              'Please set a unique name for each analyzer.'))
        self.analyzers = {analyzer.name: analyzer for analyzer in analyzers}

        self.analyzer_features = {analyzer.name: analyzer.get_feature_names()
                                  for analyzer in analyzers}
        self.db_filepath = db_filepath
        self.max_workers = max_workers or os.cpu_count() or 1
        self.continue_on_failure = continue_on_failure
        self.save_code_features = save_code_features
        self.save_occurrences = save_occurrences
        self.use_saved_features = use_saved_features

        self._runner = CodeSurveyRunner(self)

    def get_db(self):
        """Returns the Database that persists survey results."""
        return Database(self.db_filepath)

    def run(self, *,
            max_repos: Optional[int] = None,
            max_codes: Optional[int] = None,
            disable_progress: bool = False,
            progress_analyzer_features: Optional[Mapping[str, Sequence[str]]] = None):
        """Runs the survey by fetching code from sources and applying analyzers.

        If neither of the `max_repos` nor `max_codes` stopping
        conditions is specified, the survey will continue running
        until a `KeyboardInterrupt` exception.

        Args:
            max_repos: If specified, the run will stop after analysing this
                many Repos.
            max_codes: If specified, the run will stop after analysing this
                many Codes.
            disable_progress: If `True`, do not display tqdm progress bars
                counting Repos and Codes analyzed.
            progress_analyzer_features: Mapping of analyzer names to sequences
                of feature names for which progress trackers should be
                displayed to count Repos found with those features. Defaults
                to all features, but disables feature progress trackers with
                a warning when there are more than 10 features.

        """
        self._runner.run(
            max_repos=max_repos,
            max_codes=max_codes,
            disable_progress=disable_progress,
            progress_analyzer_features=progress_analyzer_features,
        )

    def get_repo_features(self, *,
                          source_names: Optional[Sequence[str]] = None,
                          analyzer_names: Optional[Sequence[str]] = None,
                          feature_names: Optional[Sequence[str]] = None) -> List[RepoFeature]:
        """Returns RepoFeatures of surveyed Repos.

        Args:
            source_names: If specified, only features from the named Sources
                will be returned.
            analyzer_names: If specified, only features from the named Analyzers
                will be returned.
            feature_names: If specified, only results for the named features
                will be returned.

        """
        return self.get_db().get_repo_features(source_names=source_names,
                                               analyzer_names=analyzer_names,
                                               feature_names=feature_names)

    def get_code_features(self, *,
                          source_names: Optional[Sequence[str]] = None,
                          analyzer_names: Optional[Sequence[str]] = None,
                          feature_names: Optional[Sequence[str]] = None) -> List[CodeFeature]:
        """Returns CodeFeatures of surveyed Codes.

        Only returns results from runs where `save_code_results` was `True`.

        Args:
            source_names: If specified, only features from the named Sources
                will be returned.
            analyzer_names: If specified, only features from the named Analyzers
                will be returned.
            feature_names: If specified, only results for the named features
                will be returned.

        """
        return self.get_db().get_code_features(source_names=source_names,
                                               analyzer_names=analyzer_names,
                                               feature_names=feature_names)

    def get_survey_tree(self, *,
                        source_names: Optional[Sequence[str]] = None,
                        analyzer_names: Optional[Sequence[str]] = None,
                        feature_names: Optional[Sequence[str]] = None) -> Dict:
        """Returns surveyed CodeFeatures and RepoFeatures structured under a
        tree structure of Sources, Repos, and Analyzers.

        Args:
            source_names: If specified, only features from the named Sources
                will be returned.
            analyzer_names: If specified, only features from the named Analyzers
                will be returned.
            feature_names: If specified, only results for the named features
                will be returned.

        Returns:
            A dictionary with the following structure:
                ```python
                {
                    'sources': {
                        '<source_name>': {
                            'repos: {
                                '<repo_key>': {
                                    'analyzers': {
                                        '<analyzer_name>': {
                                            'features': {
                                                'updated': datetime(...),
                                                'occurence_count': int(...),
                                                'code_occurrence_count': int(...),
                                                'code_total_count': int(...),
                                            },
                                            # 'codes' key is only present if
                                            # survey runs are performed with
                                            # `save_code_features=True`
                                            'codes': {
                                                '<code_key>': {
                                                    'features': {
                                                        '<feature_name>': {
                                                            'updated': datetime(...),
                                                            'occurence_count': int(...),
                                                        },
                                                        ...
                                                    }
                                                },
                                                ...
                                            }
                                        },
                                        ...
                                    },
                                    'repo_metadata': {
                                        '<metadata_key>': ...,
                                        ...
                                    }
                                },
                                ...
                            }
                        },
                        ...
                    }
                }
                ```

        """
        tree: Dict = {'sources': {}}
        code_features = self.get_code_features(source_names=source_names,
                                               analyzer_names=analyzer_names,
                                               feature_names=feature_names)
        for c in code_features:
            recursive_update(tree, {
                'sources': {c.source_name: {
                    'repos': {c.repo_key: {
                        'analyzers': {c.analyzer_name: {
                            'codes': {c.code_key: {
                                'features': {c.feature_name: {
                                    'updated': c.updated,
                                    'occurrence_count': c.occurrence_count,
                                    'occurrences': c.occurrences,
                                }}
                            }}
                        }},
                        'repo_metadata': c.repo_metadata,
                    }}
                }}
            })
        repo_features = self.get_repo_features(source_names=source_names,
                                               analyzer_names=analyzer_names)
        for r in repo_features:
            recursive_update(tree, {
                'sources': {r.source_name: {
                    'repos': {r.repo_key: {
                        'analyzers': {r.analyzer_name: {
                            'features': {r.feature_name: {
                                'updated': r.updated,
                                'occurrence_count': r.occurrence_count,
                                'code_occurrence_count': r.code_occurrence_count,
                                'code_total_count': r.code_total_count,
                            }},
                        }},
                        'repo_metadata': r.repo_metadata,
                    }}
                }}
            })
        return tree
