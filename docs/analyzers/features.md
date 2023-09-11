Each [`Analyzer`](core.md) is configured with a set of FeatureFinders
that identify occurrences of features of interest within a unit of
source-code.

A [`FeatureFinder`][codesurvey.analyzers.FeatureFinder] can be any
function with a `name` attribute that receives an object representing
a unit of source-code (the type of the object will depend on the
`Analyzer` being used) and returns a
[`Feature`][codesurvey.analyzers.Feature].

## Defining Feature Finders

The following utility functions can be used to define your own
`FeatureFinders`.

For convenience, feature finding functions wrapped with these
utilities you can return a dictionary with one of the following
structures instead of a `Feature` object:

```python
# A feature finder should typically return a list of occurrences of the
# feature in the given code_representation. Each occurrence should be a
# JSON-serializable dictionary that can capture whatever keys make sense
# for your feature.
{
    'occurrences': List[dict]
}
# Return an 'ignore' result in cases where the
# code_representation cannot be analyzed.
{
    'ignore': bool
}
```

::: codesurvey.analyzers.feature_finder
    options:
        show_signature_annotations: false

::: codesurvey.analyzers.partial_feature_finder
    options:
        show_signature_annotations: false

::: codesurvey.analyzers.union_feature_finder
    options:
        show_signature_annotations: false

## Core Classes

::: codesurvey.analyzers.FeatureFinder

::: codesurvey.analyzers.Feature
