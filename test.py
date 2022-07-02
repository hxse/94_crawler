#!/usr/bin/env python3
# coding: utf-8


def sort_playlist(data, paths):
    cursor = -1
    for p in paths:
        if p in data:
            cursor = data.index(p)
        else:
            data.insert(cursor + 1, p)
            cursor = data.index(p)

    return data


data = ["a", "b", "c", "d"]
paths = ["a", "z", "b", "a", "i"]
print(sort_playlist(data, paths))
