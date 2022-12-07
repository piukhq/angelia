from typing import Optional

from pydantic import Field

from app.api.serializers import BaseModel


class TestSubSerializer(BaseModel):
    str_test: Optional[str]
    list_test: Optional[list] = Field(default_factory=list)
    dict_test: Optional[dict]


class TestSerializer(BaseModel):
    str_test: Optional[str]
    list_test: Optional[list] = Field(default_factory=list)
    dict_test: Optional[dict]
    sub_model_test: Optional[TestSubSerializer]


def test_base_serializer():
    data = {
        "str_test": "hello",
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
    }

    data2 = {"sub_model_test": data}
    data2.update(data)

    serialized_data = TestSerializer(**data2).dict()

    assert {
        "str_test": "hello",
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
        "sub_model_test": {
            "str_test": "hello",
            "list_test": [1, "hello", "", None, {}, []],
            "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
        },
    } == serialized_data


def test_base_serializer_missing_str():
    missing_str = {
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
    }

    none_str = {
        "str_test": None,
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
    }

    expected = {
        "str_test": None,
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
        "sub_model_test": {
            "str_test": None,
            "list_test": [1, "hello", "", None, {}, []],
            "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
        },
    }

    for test in [missing_str, none_str]:
        test_data = {"sub_model_test": test}
        test_data.update(test)

        serialized_data = TestSerializer(**test_data).dict()

        assert expected == serialized_data


def test_base_serializer_missing_dict():
    missing_dict = {
        "str_test": "hello",
        "list_test": [1, "hello", "", None, {}, []],
    }

    none_dict = {"str_test": "hello", "list_test": [1, "hello", "", None, {}, []], "dict_test": None}

    empty_dict = {"str_test": "hello", "list_test": [1, "hello", "", None, {}, []], "dict_test": {}}

    expected = {
        "str_test": "hello",
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": None,
        "sub_model_test": {"str_test": "hello", "list_test": [1, "hello", "", None, {}, []], "dict_test": None},
    }

    for test in [missing_dict, none_dict, empty_dict]:
        test_data = {"sub_model_test": test}
        test_data.update(test)

        serialized_data = TestSerializer(**test_data).dict()

        assert expected == serialized_data


def test_base_serializer_missing_list():
    missing_list = {
        "str_test": "hello",
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
    }

    none_list = {
        "str_test": "hello",
        "list_test": None,
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
    }

    empty_list = {
        "str_test": "hello",
        "list_test": [],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
    }

    expected = {
        "str_test": "hello",
        "list_test": [],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
        "sub_model_test": {
            "str_test": "hello",
            "list_test": [],
            "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
        },
    }

    for test in [missing_list, none_list, empty_list]:
        test_data = {"sub_model_test": test}
        test_data.update(test)

        serialized_data = TestSerializer(**test_data).dict()

        assert expected == serialized_data


def test_base_serializer_missing_model():
    test_data = {
        "str_test": "hello",
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
    }

    none_sub_model = {**test_data, "sub_model_test": None}

    expected = {
        "str_test": "hello",
        "list_test": [1, "hello", "", None, {}, []],
        "dict_test": {"hello": "", 1: "world", "foo": None, "empty_dict": {}, "empty_list": []},
        "sub_model_test": None,
    }

    for test in [test_data, none_sub_model]:
        serialized_data = TestSerializer(**test).dict()
        assert expected == serialized_data
