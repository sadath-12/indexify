import unittest
from typing import List

from pydantic import BaseModel, Field

from indexify import Graph, RemoteGraph
from indexify.functions_sdk.indexify_functions import indexify_function


class Jokes(BaseModel):
    jokes: List[str] = Field(default_factory=list)


@indexify_function()
def generate_joke_subjects(num_subjects: int) -> List[str]:
    return ["joke subject " + str(i) for i in range(num_subjects)]


@indexify_function()
def generate_joke(subject: str) -> str:
    return f"Why did the {subject} cross the road? Because it was the only way to get to the other side!"


@indexify_function(accumulate=Jokes)
def accumulate_jokes(acc: Jokes, joke: str) -> Jokes:
    acc.jokes.append(joke)
    return acc


@indexify_function()
def best_joke(jokes: Jokes) -> str:
    return max(jokes.jokes, key=len)


def create_jokes_graph():
    graph = Graph(name="jokes", description="generate jokes")
    graph.add_edge(generate_joke_subjects, generate_joke)
    graph.add_edge(generate_joke, accumulate_jokes)
    graph.add_edge(accumulate_jokes, best_joke)
    return graph


class AccumulatedSate(BaseModel):
    sum: int = 19


@indexify_function()
def generate_seq(x: int) -> List[int]:
    return [i for i in range(x)]


@indexify_function(accumulate=AccumulatedSate)
def accumulate_reduce(acc: AccumulatedSate, y: int) -> AccumulatedSate:
    acc.sum += y
    return acc


@indexify_function()
def store_result(acc: AccumulatedSate) -> int:
    return acc.sum


def create_graph():
    graph = Graph(name="test", description="test", start_node=generate_seq)
    graph.add_edge(generate_seq, accumulate_reduce)
    graph.add_edge(accumulate_reduce, store_result)
    return graph


class TestReduce(unittest.TestCase):
    def test_reduce(self):
        graph = create_graph()
        RemoteGraph.deploy(graph)
        graph = RemoteGraph.by_name(graph.name)
        invocation_id = graph.run(block_until_done=True, x=3)
        result = graph.output(invocation_id, store_result.name)
        self.assertEqual(result[0], 22)

    def test_metadata(self):
        graph = create_graph()
        metadata = graph.definition()
        metadata_json = metadata.model_dump(exclude_none=True)
        print(metadata_json)


if __name__ == "__main__":
    unittest.main()