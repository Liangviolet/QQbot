"""U2 消息持久化存储 — 数据库层测试"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.exc import IntegrityError

from src.models.message import GroupMessage
from src.services.database import get_db_session, init_db


@pytest.fixture
async def engine():
    e = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    yield e
    await e.dispose()


@pytest.fixture
def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


class TestGroupMessage:
    """GroupMessage CRUD 操作测试"""

    async def test_happy_path_insert_and_query(self, engine, session_maker):
        """Happy path: 插入一条消息后按 user_id + group_id 查询可正确返回"""
        await init_db(engine)

        msg = GroupMessage(
            group_id=12345,
            user_id=67890,
            plain_text="Hello, world!",
            raw_message='{"text": "Hello, world!"}',
            timestamp=1716000000,
            message_id=1001,
        )
        async with get_db_session(session_maker) as session:
            session.add(msg)

        async with get_db_session(session_maker) as session:
            result = await session.execute(
                select(GroupMessage).where(
                    GroupMessage.user_id == 67890,
                    GroupMessage.group_id == 12345,
                )
            )
            fetched = result.scalar_one()
            assert fetched.plain_text == "Hello, world!"
            assert fetched.message_id == 1001
            assert fetched.id is not None  # autoincrement PK

    async def test_duplicate_message_id_raises_integrity_error(self, engine, session_maker):
        """Edge case: 相同 message_id 重复插入应捕获 IntegrityError，不崩溃"""
        await init_db(engine)

        msg1 = GroupMessage(
            group_id=1, user_id=1,
            plain_text="first", raw_message="{}",
            timestamp=100, message_id=999,
        )
        msg2 = GroupMessage(
            group_id=2, user_id=2,
            plain_text="second", raw_message="{}",
            timestamp=200, message_id=999,  # 故意重复
        )

        async with get_db_session(session_maker) as session:
            session.add(msg1)

        # 第二次插入相同 message_id 应当抛 IntegrityError
        with pytest.raises(IntegrityError):
            async with get_db_session(session_maker) as session:
                session.add(msg2)

    async def test_concurrent_insert_5_messages(self, engine, session_maker):
        """并发插入 5 条消息应全部成功"""
        await init_db(engine)

        messages = [
            GroupMessage(
                group_id=100, user_id=i,
                plain_text=f"msg {i}", raw_message="{}",
                timestamp=1000 + i, message_id=2000 + i,
            )
            for i in range(5)
        ]
        async with get_db_session(session_maker) as session:
            session.add_all(messages)

        async with get_db_session(session_maker) as session:
            result = await session.execute(
                select(GroupMessage)
                .where(GroupMessage.group_id == 100)
                .order_by(GroupMessage.timestamp)
            )
            rows = result.scalars().all()
            assert len(rows) == 5
            for i, row in enumerate(rows):
                assert row.user_id == i
                assert row.plain_text == f"msg {i}"

    async def test_db_error_has_clear_exception(self, engine, session_maker):
        """Error path: 数据库错误应有清晰异常，且数据不受影响"""
        await init_db(engine)

        msg = GroupMessage(
            group_id=10, user_id=20,
            plain_text="valid", raw_message="{}",
            timestamp=500, message_id=5000,
        )
        async with get_db_session(session_maker) as session:
            session.add(msg)

        # 重复 message_id 应抛 IntegrityError
        with pytest.raises(IntegrityError):
            async with get_db_session(session_maker) as session:
                session.add(GroupMessage(
                    group_id=10, user_id=20,
                    plain_text="dup id", raw_message="{}",
                    timestamp=501, message_id=5000,
                ))

        # 验证原始数据未被破坏
        async with get_db_session(session_maker) as session:
            result = await session.execute(
                select(GroupMessage).where(GroupMessage.message_id == 5000)
            )
            assert result.scalar_one().plain_text == "valid"
