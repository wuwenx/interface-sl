"""数据库连接和会话管理"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
from app.utils.logger import logger

# 创建基础模型类（先创建，避免循环导入）
Base = declarative_base()

# 延迟初始化数据库引擎（在需要时创建）
engine = None
AsyncSessionLocal = None


def init_database_engine():
    """初始化数据库引擎（延迟初始化）"""
    global engine, AsyncSessionLocal
    
    if engine is not None:
        return
    
    try:
        # 创建异步数据库引擎
        DATABASE_URL = (
            f"mysql+aiomysql://{settings.db_user}:{settings.db_password}"
            f"@{settings.db_host}:{settings.db_port}/{settings.db_name}?charset={settings.db_charset}"
        )
        
        engine = create_async_engine(
            DATABASE_URL,
            echo=settings.debug,  # 是否打印SQL语句
            pool_pre_ping=True,  # 连接池预检查
            pool_recycle=3600,  # 连接回收时间（秒）
        )
        
        # 创建异步会话工厂
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        logger.info("数据库引擎初始化成功")
    except Exception as e:
        logger.warning(f"数据库引擎初始化失败: {e}")
        raise


async def get_db():
    """
    获取数据库会话（依赖注入）
    如果数据库连接失败，返回None而不是抛出异常
    
    Yields:
        AsyncSession | None: 数据库会话，如果连接失败则为None
    """
    global AsyncSessionLocal
    
    if AsyncSessionLocal is None:
        try:
            init_database_engine()
        except Exception as e:
            logger.warning(f"数据库连接失败，缓存功能将不可用: {e}")
            yield None
            return
    
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    except Exception as e:
        logger.warning(f"数据库会话创建失败: {e}")
        yield None


async def init_db():
    """初始化数据库，创建所有表"""
    from app.models import db_models  # noqa: F401  # 确保 CcxtMarketsCache 等表已注册
    if engine is None:
        init_database_engine()
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表创建完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


async def close_db():
    """关闭数据库连接"""
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None
        logger.info("数据库连接已关闭")
