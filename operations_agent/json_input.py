"""Strict JSON decoding shared by file input and untrusted model output."""
import json


def unique_json_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate JSON field names are not allowed')
        result[name] = value
    return result


def reject_json_constant(value):
    raise ValueError('NaN and Infinity are not valid JSON numbers')


def load_json(text):
    return json.loads(text, object_pairs_hook=unique_json_object,
                      parse_constant=reject_json_constant)
