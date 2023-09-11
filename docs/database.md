CodeSurvey saves survey results into an
[sqlite](https://www.sqlite.org/) database that can be queried
directly, such as by using the [sqlite
CLI](https://sqlite.org/cli.html) or Python's
[`sqlite3`](https://docs.python.org/3/library/sqlite3.html) module.

The database has the following tables:

## `repo_metadata`

There is one `repo_metadata` row for each entry of metadata for each Repo.

| Column           | Key | Data type | Description                                       |
|------------------|-----|-----------|---------------------------------------------------|
| `source_name`    | PK  | `VARCHAR` | Name of the Source that produced the target Repo  |
| `repo_key`       | PK  | `VARCHAR` | Key identifying the target Repo within the Source |
| `metadata_key`   | PK  | `VARCHAR` | Key of this metadata entry                        |
| `metadata_value` |     | `JSON`    | Value associated with the metadata key            |
| `updated`        |     | `INTEGER` | Timestamp when this metadata was last updated     |

## `repo_feature`

There is one `repo_feature` row for each Analyzer feature surveyed
over all Codes for each Repo.

| Column                  | Key | Data type | Description                                                     |
|-------------------------|-----|-----------|-----------------------------------------------------------------|
| `source_name`           | PK  | `VARCHAR` | Name of the Source that produced the target Repo                |
| `repo_key`              | PK  | `VARCHAR` | Key identifying the target Repo within the Source               |
| `analyzer_name`         | PK  | `VARCHAR` | Name of the Analyzer that produced this feature                 |
| `feature_name`          | PK  | `VARCHAR` | Name of the analyzed feature                                    |
| `occurrence_count`      |     | `INTEGER` | Number of occurrences of this feature within the Repo           |
| `code_occurrence_count` |     | `INTEGER` | Number of Codes within the Repo containing this feature         |
| `code_total_count`      |     | `INTEGER` | Total number of Codes analyzed for this feature within the Repo |
| `updated`               |     | `INTEGER` | Timestamp when this analysis was last updated                   |

## `code_feature`

There is one `code_feature` row for each Analyzer feature surveyed
over each Code from a Repo.

| Column             | Key | Data type | Description                                                                                                                                                    |
|--------------------|-----|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `source_name`      | PK  | `VARCHAR` | Name of the Source that produced the target Repo                                                                                                               |
| `repo_key`         | PK  | `VARCHAR` | Key identifying the target Repo within the Source                                                                                                              |
| `analyzer_name`    | PK  | `VARCHAR` | Name of the Analyzer that produced this feature                                                                                                                |
| `feature_name`     | PK  | `VARCHAR` | Name of the analyzed feature                                                                                                                                   |
| `code_key`         | PK  | `VARCHAR` | Key idenfitying the target Code within the Repo                                                                                                                |
| `occurrence_count` |     | `INTEGER` | Number of occurrences of this feature within the Code, or `NULL` if analysis of this Code was skipped                                                          |
| `occurrences`      |     | `JSON`    | Original occurrence objects returned by FeatureFinders, or `NULL` if analysis of this Code was skipped or `save_occurrences` was not enabled on the CodeSurvey |
| `updated`          |     | `INTEGER` | Timestamp when this analysis was last updated                                                                                                                  |

