from pydantic import BaseModel
from indexify import indexify_function, Graph
from typing import List

class Total(BaseModel):
    val: int = 0

@indexify_function()
def generate_numbers(a: int) -> List[int]:
    return {}

@indexify_function()
def square(x: int) -> int:
    return x ** 2

@indexify_function(accumulate=Total)
def add(total: Total, new: int) -> Total:
    total.val += new
    return total

g = Graph(name="sequence_summer1", start_node=generate_numbers, description="Simple Sequence Summer")
g.add_edge(generate_numbers, square)
g.add_edge(square, add)

if __name__ == "__main__":


    from indexify import RemoteGraph
    graph = RemoteGraph.deploy(g,server_url="http://localhost:8900")
    invocation_id = graph.run(block_until_done=True, a=10)
    result = graph.output(invocation_id, "add")
    print(result)

    # graph = RemoteGraph.by_name("sequence_summer",server_url="http://localhost:8900")
    # invocation_id = graph.run(block_until_done=True, a=5)
    # print(graph.output(invocation_id, "add"))
