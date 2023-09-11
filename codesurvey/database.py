"""Database interaction layer for storing and retrieving survey results."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from playhouse.sqlite_ext import (
    SqliteExtDatabase,
    Model,
    CharField,
    TimestampField,
    IntegerField,
    JSONField,
    CompositeKey,
    fn,
)

from codesurvey.sources import Repo
from codesurvey.analyzers import Code


@dataclass(frozen=True)
class RepoFeature:
    updated: datetime
    """Timestamp when this analysis was last updated."""

    source_name: str
    """Name of the Source that produced the target Repo."""

    repo_key: str
    """Key identifying the target Repo within the Source."""

    analyzer_name: str
    """Name of the Analyzer that produced this feature."""

    feature_name: str
    """Name of the analyzed feature."""

    occurrence_count: int
    """Number of occurrences of this feature within the Repo."""

    code_occurrence_count: int
    """Number of Codes within the Repo containing this feature."""

    code_total_count: int
    """Total number of Codes analyzed for this feature within the Repo."""

    repo_metadata: Dict[str, Any]
    """Metadata of the Repo provided by the Source."""


@dataclass(frozen=True)
class CodeFeature:
    updated: datetime
    """Timestamp when this analysis was last updated."""

    source_name: str
    """Name of the Source that produced the target Repo."""

    repo_key: str
    """Key identifying the target Repo within the Source."""

    analyzer_name: str
    """Name of the Analyzer that produced this feature."""

    code_key: str
    """Key idenfitying the target Code within the Repo."""

    feature_name: str
    """Name of the analyzed feature."""

    occurrence_count: Optional[int]
    """Number of occurrences of this feature within the Code, or `None` if
    analysis of this Code was skipped."""

    occurrences: Optional[List[Dict[str, Any]]]
    """Original occurrence objects returned by FeatureFinders."""

    repo_metadata: Dict[str, Any]
    """Metadata of the Repo provided by the Source."""


class MetadataCache(Protocol):
    """Memoized function for retrieving Repo metadata."""

    def __call__(self, *, source_name: str, repo_key: str) -> Dict[str, Any]:
        pass


class Database:
    """Stores and fetches survey results from an sqlite database."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.db = SqliteExtDatabase(self.filepath)

        class BaseModel(Model):
            class Meta:
                database = self.db

            @classmethod
            def get_primary_key_columns(cls):
                return [
                    getattr(cls, column_name)
                    for column_name in self.db.get_primary_keys(cls._meta.table_name)
                ]

        class RepoMetadataModel(BaseModel):
            class Meta:
                table_name = 'repo_metadata'
                primary_key = CompositeKey(
                    'source_name',
                    'repo_key',
                    'metadata_key',
                )

            updated = TimestampField()
            source_name = CharField()
            repo_key = CharField()
            metadata_key = CharField()
            metadata_value = JSONField()

        class RepoFeatureModel(BaseModel):
            class Meta:
                table_name = 'repo_feature'
                primary_key = CompositeKey(
                    'source_name',
                    'repo_key',
                    'analyzer_name',
                    'feature_name',
                )

            updated = TimestampField()
            source_name = CharField()
            repo_key = CharField()
            analyzer_name = CharField()
            feature_name = CharField()
            occurrence_count = IntegerField()
            code_occurrence_count = IntegerField()
            code_total_count = IntegerField()

        class CodeFeatureModel(BaseModel):
            class Meta:
                table_name = 'code_feature'
                primary_key = CompositeKey(
                    'source_name',
                    'repo_key',
                    'analyzer_name',
                    'code_key',
                    'feature_name',
                )

            updated = TimestampField()
            source_name = CharField()
            repo_key = CharField()
            analyzer_name = CharField()
            code_key = CharField()
            feature_name = CharField()
            # null occurrence_count or occurrences indicates an ignored code.
            occurrence_count = IntegerField(null=True)
            occurrences = JSONField(null=True)

        self.RepoMetadataModel = RepoMetadataModel
        self.RepoFeatureModel = RepoFeatureModel
        self.CodeFeatureModel = CodeFeatureModel
        self.tables = [self.RepoMetadataModel, self.RepoFeatureModel, self.CodeFeatureModel]

    def initialize(self):
        """Connect to the database and initialize the schema."""
        self.db.connect()
        self.db.create_tables(self.tables)

    def close(self):
        """Close the database."""
        self.db.close()

    def get_repo_missing_analyzer_features(
        self, *,
        source_name: str,
        repo_key: str,
        analyzer_features: Mapping[str, Sequence[str]],
    ) -> Dict[str, List[str]]:
        """Filter the given analyzer_features to those not recorded for a
        given Repo.

        Args:
            source_name: Name of the target Repo's Source
            repo_key: Key of the target Repo
            analyzer_features: Mapping of Analyzer names to feature names

        """
        rows = (self.RepoFeatureModel
                .select(
                    self.RepoFeatureModel.analyzer_name,
                    self.RepoFeatureModel.feature_name,
                )
                .distinct(True)
                .where(
                    (self.RepoFeatureModel.source_name == source_name)
                    & (self.RepoFeatureModel.repo_key == repo_key)
                    & (self.RepoFeatureModel.analyzer_name.in_(list(analyzer_features.keys())))))
        existing_analyzer_features = defaultdict(set)
        for row in rows:
            existing_analyzer_features[row.analyzer_name].add(row.feature_name)

        missing_analyzer_features = {}
        for analyzer_name, features in analyzer_features.items():
            missing_features = [
                feature for feature in features
                if feature not in existing_analyzer_features[analyzer_name]
            ]
            if len(missing_features) > 0:
                missing_analyzer_features[analyzer_name] = missing_features
        return missing_analyzer_features

    def get_code_missing_features(
        self, *,
        source_name: str,
        repo_key: str,
        code_key: str,
        analyzer_name: str,
        features: Sequence[str],
    ) -> Sequence[str]:
        """Filter the given features to those not recorded for a given Code.

        Args:
            source_name: Name of the target Repo's Source
            repo_key: Key of the target Repo
            code_key: Key of the target Code
            analyzer_name: Name of the Analyzer to get features for
            features: Names of the Analyzer's features

        """
        rows = (self.CodeFeatureModel
                .select(self.CodeFeatureModel.feature_name)
                .distinct(True)
                .where(
                    (self.CodeFeatureModel.source_name == source_name)
                    & (self.CodeFeatureModel.repo_key == repo_key)
                    & (self.CodeFeatureModel.analyzer_name == analyzer_name)
                    & (self.CodeFeatureModel.code_key == code_key)
                    & (self.CodeFeatureModel.feature_name.in_(features))))
        existing_features = set([row.feature_name for row in rows])
        return [
            feature for feature in features
            if feature not in existing_features
        ]

    def save_repo_metadata(self, repo: Repo):
        """Save metadata for the given Repo."""
        with self.db.atomic():
            (self.RepoMetadataModel
             .insert_many([
                 dict(
                     updated=datetime.now(),
                     source_name=repo.source.name,
                     repo_key=repo.key,
                     metadata_key=metadata_key,
                     metadata_value=metadata_value,
                 )
                 for metadata_key, metadata_value in repo.metadata.items()
             ])
             .on_conflict(
                 conflict_target=self.RepoMetadataModel.get_primary_key_columns(),
                 preserve=[
                     self.RepoMetadataModel.updated,
                     self.RepoMetadataModel.metadata_value,
                 ],
             )
             .execute())

    def save_code_features(self, code: Code, *, save_occurrences: bool):
        """Save Analyzer features for the given Code.

        Only save the raw occurrence objects if save_occurrences is
        `True`.

        """
        with self.db.atomic():
            (self.CodeFeatureModel
             .insert_many([
                 dict(
                     updated=datetime.now(),
                     source_name=code.repo.source.name,
                     repo_key=code.repo.key,
                     analyzer_name=code.analyzer.name,
                     code_key=code.key,
                     feature_name=feature_name,
                     occurrence_count=(
                         None if feature.ignore else len(feature.occurrences)
                     ),
                     occurrences=(
                         None if (feature.ignore or not save_occurrences)
                         else feature.occurrences
                     ),
                 )
                 for feature_name, feature in code.features.items()
             ])
             .on_conflict(
                 conflict_target=self.CodeFeatureModel.get_primary_key_columns(),
                 preserve=[
                     self.CodeFeatureModel.updated,
                     self.CodeFeatureModel.occurrence_count,
                     self.CodeFeatureModel.occurrences,
                 ],
             )
             .execute())

    def save_repo_features(self, repo: Repo, *, keep_code_features: bool):
        """Save Analyzer features for the given Repo by aggregating Code
        features.

        If keep_code_features=False, delete the Code features for the
        Repo after saving Analyzer features.

        """
        repo_code_filter = ((self.CodeFeatureModel.source_name == repo.source.name)
                            & (self.CodeFeatureModel.repo_key == repo.key))
        (self.RepoFeatureModel
         .insert_from(
             query=(self.CodeFeatureModel
                    .select(
                        # Most recent CodeFeatureModel updated time
                        fn.MAX(self.CodeFeatureModel.updated),
                        self.CodeFeatureModel.source_name,
                        self.CodeFeatureModel.repo_key,
                        self.CodeFeatureModel.analyzer_name,
                        self.CodeFeatureModel.feature_name,
                        # Sum of all occurrences in CodeFeatureModels
                        fn.SUM(self.CodeFeatureModel.occurrence_count),
                        # Count of all CodeFeatureModels with at least one occurrence
                        fn.SUM(fn.MAX(self.CodeFeatureModel.occurrence_count, 1)),
                        # Count of all CodeFeatureModels
                        fn.COUNT(),
                    )
                    .where(repo_code_filter
                           # Do not count "ignored" CodeFeatureModels
                           & self.CodeFeatureModel.occurrence_count.is_null(False))
                    .group_by(self.CodeFeatureModel.feature_name)),
             fields=[
                 self.RepoFeatureModel.updated,
                 self.RepoFeatureModel.source_name,
                 self.RepoFeatureModel.repo_key,
                 self.RepoFeatureModel.analyzer_name,
                 self.RepoFeatureModel.feature_name,
                 self.RepoFeatureModel.occurrence_count,
                 self.RepoFeatureModel.code_occurrence_count,
                 self.RepoFeatureModel.code_total_count,
             ],
         )
         .on_conflict(
             conflict_target=self.RepoFeatureModel.get_primary_key_columns(),
             preserve=[
                 self.RepoFeatureModel.updated,
                 self.RepoFeatureModel.occurrence_count,
                 self.RepoFeatureModel.code_occurrence_count,
                 self.RepoFeatureModel.code_total_count,
             ],
         )
         .execute())

        # Optionally delete matched CodeFeatureModel rows to reduce storage.
        if not keep_code_features:
            (self.CodeFeatureModel
             .delete()
             .where(repo_code_filter)
             .execute())

    def _get_repo_metadata(self, *, source_name: str, repo_key: str) -> Dict[str, Any]:
        """Retrieves metadata for a given Repo from the database."""
        rows = (self.RepoMetadataModel
                .select(
                    self.RepoMetadataModel.metadata_key,
                    self.RepoMetadataModel.metadata_value,
                )
                .where((self.RepoMetadataModel.source_name == source_name)
                       & (self.RepoMetadataModel.repo_key == repo_key)))
        return {
            row.metadata_key: row.metadata_value
            for row in rows
        }

    def _get_repo_metadata_cache(self) -> MetadataCache:
        """Returns a function that returns the metadata for a given Repo with
        caching to prevent repeated database queries."""
        cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

        def metadata_cache(*, source_name: str, repo_key: str) -> Dict[str, Any]:
            cache_key = (source_name, repo_key)
            if cache_key not in cache:
                cache[cache_key] = self._get_repo_metadata(source_name=source_name, repo_key=repo_key)
            return cache[cache_key]

        return metadata_cache

    def get_repo_features(self, *,
                          source_names: Optional[Sequence[str]] = None,
                          repo_keys: Optional[Sequence[str]] = None,
                          analyzer_names: Optional[Sequence[str]] = None,
                          feature_names: Optional[Sequence[str]] = None) -> List[RepoFeature]:
        """Returns RepoFeatures of surveyed Repos.

        Args:
            source_names: If specified, only features from the named Sources
                will be returned.
            repo_keys: If specified, only features from the named Repos
                will be returned.
            analyzer_names: If specified, only features from the named Analyzers
                will be returned.
            feature_names: If specified, only results for the named features
                will be returned.

        """
        query = self.RepoFeatureModel.select()
        if source_names is not None:
            query = query.where(self.RepoFeatureModel.source_name.in_(source_names))
        if repo_keys is not None:
            query = query.where(self.RepoFeatureModel.repo_key.in_(repo_keys))
        if analyzer_names is not None:
            query = query.where(self.RepoFeatureModel.analyzer_name.in_(analyzer_names))
        if feature_names is not None:
            query = query.where(self.RepoFeatureModel.feature_name.in_(feature_names))

        metadata_cache = self._get_repo_metadata_cache()
        return [
            RepoFeature(
                **row,
                repo_metadata=metadata_cache(source_name=row['source_name'],
                                             repo_key=row['repo_key']),
            )
            for row in query.dicts()
        ]

    def get_code_features(self, *,
                          source_names: Optional[Sequence[str]] = None,
                          repo_keys: Optional[Sequence[str]] = None,
                          analyzer_names: Optional[Sequence[str]] = None,
                          feature_names: Optional[Sequence[str]] = None) -> List[CodeFeature]:
        """Returns CodeFeatures of surveyed Codes.

        Args:
            source_names: If specified, only features from the named Sources
                will be returned.
            repo_keys: If specified, only features from the named Repos
                will be returned.
            analyzer_names: If specified, only features from the named Analyzers
                will be returned.
            feature_names: If specified, only results for the named features
                will be returned.

        """
        query = self.CodeFeatureModel.select()
        if source_names is not None:
            query = query.where(self.CodeFeatureModel.source_name.in_(source_names))
        if repo_keys is not None:
            query = query.where(self.RepoFeatureModel.repo_key.in_(repo_keys))
        if analyzer_names is not None:
            query = query.where(self.CodeFeatureModel.analyzer_name.in_(analyzer_names))
        if feature_names is not None:
            query = query.where(self.RepoFeatureModel.feature_name.in_(feature_names))

        metadata_cache = self._get_repo_metadata_cache()
        return [
            CodeFeature(
                **row,
                repo_metadata=metadata_cache(source_name=row['source_name'],
                                             repo_key=row['repo_key']),
            )
            for row in query.dicts()
        ]
