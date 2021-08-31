from functools import partial
import json
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock

from yapapi import WorkContext
from yapapi.events import CommandExecuted
from yapapi.script import Script


@pytest.mark.skipif(sys.version_info < (3, 8), reason="AsyncMock requires python 3.8+")
class TestScript:
    @pytest.fixture(autouse=True)
    def setUp(self):
        self._on_download_executed = False

    @pytest.fixture
    def work_context(self):
        return WorkContext(MagicMock(), MagicMock(), storage=AsyncMock())

    @staticmethod
    def _assert_dst_path(script: Script, dst_path):
        batch = script._evaluate()
        # transfer_cmd = {'transfer': {'from': 'some/mock/path', 'to': 'container:expected/path'}
        transfer_cmd = [cmd for cmd in batch if "transfer" in cmd][0]
        assert transfer_cmd["transfer"]["to"] == f"container:{dst_path}"

    @staticmethod
    def _assert_src_path(script: Script, src_path):
        batch = script._evaluate()
        # transfer_cmd = {'transfer': {'from': 'container:expected/path', 'to': 'some/mock/path'}
        transfer_cmd = [cmd for cmd in batch if "transfer" in cmd][0]
        assert transfer_cmd["transfer"]["from"] == f"container:{src_path}"

    async def _on_download(self, expected, data: bytes):
        assert data == expected
        self._on_download_executed = True

    @pytest.mark.asyncio
    async def test_send_json(self, work_context: WorkContext):
        storage: AsyncMock = work_context._storage
        dst_path = "/test/path"
        data = {
            "param": "value",
        }

        script = work_context.new_script()
        script.send_json(data, dst_path)
        await script._before()

        storage.upload_bytes.assert_called_with(json.dumps(data).encode("utf-8"))
        self._assert_dst_path(script, dst_path)

    @pytest.mark.asyncio
    async def test_send_bytes(self, work_context: WorkContext):
        storage: AsyncMock = work_context._storage
        dst_path = "/test/path"
        data = b"some byte string"

        script = work_context.new_script()
        script.send_bytes(data, dst_path)
        await script._before()

        storage.upload_bytes.assert_called_with(data)
        self._assert_dst_path(script, dst_path)

    @pytest.mark.asyncio
    async def test_download_bytes(self, work_context: WorkContext):
        expected = b"some byte string"
        storage: AsyncMock = work_context._storage
        storage.new_destination.return_value.download_bytes.return_value = expected
        src_path = "/test/path"

        script = work_context.new_script()
        script.download_bytes(src_path, partial(self._on_download, expected))
        await script._before()
        await script._after()

        self._assert_src_path(script, src_path)
        assert self._on_download_executed

    @pytest.mark.asyncio
    async def test_download_json(self, work_context: WorkContext):
        expected = {"key": "val"}
        storage: AsyncMock = work_context._storage
        storage.new_destination.return_value.download_bytes.return_value = json.dumps(
            expected
        ).encode("utf-8")
        src_path = "/test/path"

        script = work_context.new_script()
        script.download_json(src_path, partial(self._on_download, expected))
        await script._before()
        await script._after()

        self._assert_src_path(script, src_path)
        assert self._on_download_executed

    @pytest.mark.asyncio
    async def test_implicit_init(self, work_context: WorkContext):
        script = work_context.new_script()

        # first script, should include implicit deploy and start cmds
        await script._before()
        assert len(script._commands) == 2
        deploy_cmd = script._commands[0]
        start_cmd = script._commands[1]
        # report cmds as executed to flip work_context._started
        script._set_cmd_result(
            CommandExecuted("job_id", "agr_id", "script_id", 0, command=deploy_cmd)
        )
        script._set_cmd_result(
            CommandExecuted("job_id", "agr_id", "script_id", 1, command=start_cmd)
        )

        assert work_context._started

        # second script, should not include implicit deploy and start
        script = work_context.new_script()
        await script._before()
        assert len(script._commands) == 0
