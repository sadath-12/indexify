import sys
import threading
import unittest
from typing import Any, Dict, List

from pydantic import BaseModel

from indexify import Graph
from indexify.function_executor.proto.function_executor_pb2 import (
    GetInvocationStateRequest,
    GetInvocationStateResponse,
    InitializeRequest,
    InitializeResponse,
    InvocationStateRequest,
    InvocationStateResponse,
    RunTaskResponse,
    SerializedObject,
    SetInvocationStateRequest,
    SetInvocationStateResponse,
)
from indexify.function_executor.proto.function_executor_pb2_grpc import (
    FunctionExecutorStub,
)
from indexify.functions_sdk.indexify_functions import (
    get_ctx,
    indexify_function,
)
from indexify.functions_sdk.object_serializer import CloudPickleSerializer
from tests.function_executor.utils import (
    FunctionExecutorServerTestCase,
    deserialized_function_output,
    run_task,
)
from tests.testing import test_graph_name


class StructuredField(BaseModel):
    list: List[int]
    dictionary: Dict[str, Any]


class StructuredState(BaseModel):
    string: str
    integer: int
    structured: StructuredField


def invocation_state_client_stub(
    test_case: unittest.TestCase,
    stub: FunctionExecutorStub,
    expected_requests: List[InvocationStateRequest],
    responses: List[InvocationStateResponse],
) -> threading.Thread:
    server_request_iterator = stub.initialize_invocation_state_server(iter(responses))

    def loop():
        for expected_request in expected_requests:
            request = next(server_request_iterator)
            request: InvocationStateRequest
            test_case.assertEqual(request.request_id, expected_request.request_id)
            test_case.assertEqual(request.task_id, expected_request.task_id)
            if request.HasField("set"):
                test_case.assertEqual(request.set.key, expected_request.set.key)
                # Two different serialized objects are not equal so we need to deserialize them.
                test_case.assertEqual(
                    CloudPickleSerializer.deserialize(request.set.value.bytes),
                    CloudPickleSerializer.deserialize(expected_request.set.value.bytes),
                )
            else:
                test_case.assertEqual(request.get.key, expected_request.get.key)

    invocation_state_client_thread = threading.Thread(target=loop)
    invocation_state_client_thread.start()
    return invocation_state_client_thread


class TestSetInvocationState(FunctionExecutorServerTestCase):
    def _create_graph(self):
        @indexify_function()
        def set_invocation_state(x: int) -> str:
            get_ctx().invocation_state.set(
                "test_state_key",
                StructuredState(
                    string="hello",
                    integer=x,
                    structured=StructuredField(
                        list=[1, 2, 3], dictionary={"a": 1, "b": 2}
                    ),
                ),
            )
            return "success"

        return Graph(
            name=test_graph_name(self),
            description="test",
            start_node=set_invocation_state,
        )

    def _initialize_function_executor(self, stub: FunctionExecutorStub):
        graph = self._create_graph()
        initialize_response: InitializeResponse = stub.initialize(
            InitializeRequest(
                namespace="test",
                graph_name="test",
                graph_version=1,
                function_name="set_invocation_state",
                graph=SerializedObject(
                    bytes=CloudPickleSerializer.serialize(
                        graph.serialize(additional_modules=[sys.modules[__name__]])
                    ),
                    content_type=CloudPickleSerializer.content_type,
                ),
            )
        )
        self.assertTrue(initialize_response.success)

    def test_success(self):
        with self._rpc_channel() as channel:
            stub: FunctionExecutorStub = FunctionExecutorStub(channel)
            self._initialize_function_executor(stub)
            expected_requests = [
                InvocationStateRequest(
                    request_id="0",
                    task_id="test-task",
                    set=SetInvocationStateRequest(
                        key="test_state_key",
                        value=SerializedObject(
                            content_type=CloudPickleSerializer.content_type,
                            bytes=CloudPickleSerializer.serialize(
                                StructuredState(
                                    string="hello",
                                    integer=42,
                                    structured=StructuredField(
                                        list=[1, 2, 3], dictionary={"a": 1, "b": 2}
                                    ),
                                )
                            ),
                        ),
                    ),
                ),
            ]
            responses = [
                InvocationStateResponse(
                    request_id="0", success=True, set=SetInvocationStateResponse()
                ),
            ]
            client_thread = invocation_state_client_stub(
                self, stub, expected_requests, responses
            )
            run_task_response: RunTaskResponse = run_task(stub, 42)
            self.assertTrue(run_task_response.success)
            fn_outputs = deserialized_function_output(
                self, run_task_response.function_output
            )
            self.assertEqual(len(fn_outputs), 1)
            self.assertEqual("success", fn_outputs[0])

            print(
                "Joining invocation state client thread, it should exit immediately..."
            )
            client_thread.join()

    def test_client_failure(self):
        with self._rpc_channel() as channel:
            stub: FunctionExecutorStub = FunctionExecutorStub(channel)
            self._initialize_function_executor(stub)
            expected_requests = [
                InvocationStateRequest(
                    request_id="0",
                    task_id="test-task",
                    set=SetInvocationStateRequest(
                        key="test_state_key",
                        value=SerializedObject(
                            content_type=CloudPickleSerializer.content_type,
                            bytes=CloudPickleSerializer.serialize(
                                StructuredState(
                                    string="hello",
                                    integer=42,
                                    structured=StructuredField(
                                        list=[1, 2, 3], dictionary={"a": 1, "b": 2}
                                    ),
                                )
                            ),
                        ),
                    ),
                ),
            ]
            responses = [
                InvocationStateResponse(
                    request_id="0", success=False, set=SetInvocationStateResponse()
                ),
            ]
            client_thread = invocation_state_client_stub(
                self, stub, expected_requests, responses
            )
            run_task_response: RunTaskResponse = run_task(stub, 42)
            self.assertFalse(run_task_response.success)
            self.assertTrue(
                'RuntimeError("failed to set the invocation state for key")'
                in run_task_response.stderr
            )

            print(
                "Joining invocation state client thread, it should exit immediately..."
            )
            client_thread.join()


class TestGetInvocationState(FunctionExecutorServerTestCase):
    def _create_graph_with_result_validation(self):
        @indexify_function()
        def get_invocation_state(x: int) -> str:
            got_state: StructuredState = get_ctx().invocation_state.get(
                "test_state_key"
            )
            expected_state: StructuredState = StructuredState(
                string="hello",
                integer=x,
                structured=StructuredField(list=[1, 2, 3], dictionary={"a": 1, "b": 2}),
            )
            return "success" if got_state == expected_state else "failure"

        return Graph(
            name=test_graph_name(self),
            description="test",
            start_node=get_invocation_state,
        )

    def _initialize_function_executor(self, graph: Graph, stub: FunctionExecutorStub):
        initialize_response: InitializeResponse = stub.initialize(
            InitializeRequest(
                namespace="test",
                graph_name="test",
                graph_version=1,
                function_name="get_invocation_state",
                graph=SerializedObject(
                    bytes=CloudPickleSerializer.serialize(
                        graph.serialize(additional_modules=[sys.modules[__name__]])
                    ),
                    content_type=CloudPickleSerializer.content_type,
                ),
            )
        )
        self.assertTrue(initialize_response.success)

    def test_success(self):
        with self._rpc_channel() as channel:
            stub: FunctionExecutorStub = FunctionExecutorStub(channel)
            self._initialize_function_executor(
                self._create_graph_with_result_validation(), stub
            )
            expected_requests = [
                InvocationStateRequest(
                    request_id="0",
                    task_id="test-task",
                    get=GetInvocationStateRequest(
                        key="test_state_key",
                    ),
                ),
            ]
            responses = [
                InvocationStateResponse(
                    request_id="0",
                    success=True,
                    get=GetInvocationStateResponse(
                        key="test_state_key",
                        value=SerializedObject(
                            content_type=CloudPickleSerializer.content_type,
                            bytes=CloudPickleSerializer.serialize(
                                StructuredState(
                                    string="hello",
                                    integer=33,
                                    structured=StructuredField(
                                        list=[1, 2, 3], dictionary={"a": 1, "b": 2}
                                    ),
                                )
                            ),
                        ),
                    ),
                ),
            ]
            client_thread = invocation_state_client_stub(
                self, stub, expected_requests, responses
            )
            run_task_response: RunTaskResponse = run_task(stub, 33)
            self.assertTrue(run_task_response.success)
            fn_outputs = deserialized_function_output(
                self, run_task_response.function_output
            )
            self.assertEqual(len(fn_outputs), 1)
            self.assertEqual("success", fn_outputs[0])

            print(
                "Joining invocation state client thread, it should exit immediately..."
            )
            client_thread.join()

    def test_success_none_value(self):
        @indexify_function()
        def get_invocation_state(x: int) -> str:
            got_state: StructuredState = get_ctx().invocation_state.get(
                "test_state_key"
            )
            return "success" if got_state is None else "failure"

        graph = Graph(
            name=test_graph_name(self),
            description="test",
            start_node=get_invocation_state,
        )

        with self._rpc_channel() as channel:
            stub: FunctionExecutorStub = FunctionExecutorStub(channel)
            self._initialize_function_executor(graph, stub)
            expected_requests = [
                InvocationStateRequest(
                    request_id="0",
                    task_id="test-task",
                    get=GetInvocationStateRequest(
                        key="test_state_key",
                    ),
                ),
            ]
            responses = [
                InvocationStateResponse(
                    request_id="0",
                    success=True,
                    get=GetInvocationStateResponse(
                        key="test_state_key",
                        value=None,
                    ),
                ),
            ]
            client_thread = invocation_state_client_stub(
                self, stub, expected_requests, responses
            )
            run_task_response: RunTaskResponse = run_task(stub, 33)
            self.assertTrue(run_task_response.success)
            fn_outputs = deserialized_function_output(
                self, run_task_response.function_output
            )
            self.assertEqual(len(fn_outputs), 1)
            self.assertEqual("success", fn_outputs[0])

            print(
                "Joining invocation state client thread, it should exit immediately..."
            )
            client_thread.join()

    def test_client_failure(self):
        with self._rpc_channel() as channel:
            stub: FunctionExecutorStub = FunctionExecutorStub(channel)
            self._initialize_function_executor(
                self._create_graph_with_result_validation(), stub
            )
            expected_requests = [
                InvocationStateRequest(
                    request_id="0",
                    task_id="test-task",
                    get=GetInvocationStateRequest(
                        key="test_state_key",
                    ),
                ),
            ]
            responses = [
                InvocationStateResponse(
                    request_id="0",
                    success=False,
                    get=GetInvocationStateResponse(key="test_state_key"),
                ),
            ]
            client_thread = invocation_state_client_stub(
                self, stub, expected_requests, responses
            )
            run_task_response: RunTaskResponse = run_task(stub, 14)
            self.assertFalse(run_task_response.success)
            self.assertTrue(
                'RuntimeError("failed to get the invocation state for key")'
                in run_task_response.stderr
            )

            print(
                "Joining invocation state client thread, it should exit immediately..."
            )
            client_thread.join()


if __name__ == "__main__":
    unittest.main()
