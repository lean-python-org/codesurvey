from codesurvey.utils import (
    get_duplicates,
    recursive_update,
)


def test_get_duplicates():
    assert get_duplicates([]) == []
    assert get_duplicates([3, 2, 1]) == []
    assert get_duplicates([1, 2, 3, 3, 1, 2, 1]) == [3, 1, 2]
    assert get_duplicates(['1', '2', '3', '3', '1', '2', '1']) == ['3', '1', '2']
    assert get_duplicates([None, None]) == [None]


def test_recursive_update():
    test_dict = {}
    recursive_update(test_dict, {})
    assert test_dict == {}

    test_dict = {'a': {1: 'I'}, 'b': {}}
    recursive_update(test_dict, {})
    assert test_dict == {'a': {1: 'I'}, 'b': {}}

    test_dict = {'a': {1: 'I'}, 'b': {}}
    recursive_update(test_dict, {'a': {1: 'i', 2: 'ii'}, 'b': 'test'})
    assert test_dict == {'a': {1: 'I', 2: 'ii'}, 'b': {}}
