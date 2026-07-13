"""
Модуль для управления резервными копиями базы данных SQLite.
Поддерживает автоматическое и ручное создание бэкапов, а также восстановление.
"""
import os
import shutil
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple
import aiosqlite
from aiogram import Bot, types
import config
import database as db

logger = logging.getLogger(__name__)
UZ_TZ = timezone(timedelta(hours=5))

# Директория для хранения бэкапов
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

# Временные файлы для восстановления
TEMP_DB = "temp_restore.db"
TEMP_BACKUP = "temp_backup_before_restore.db"


class BackupManager:
    """Управление резервными копиями базы данных"""
    
    @staticmethod
    async def create_backup(backup_name: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Создает резервную копию базы данных.
        
        Args:
            backup_name: Имя файла бэкапа (если None - генерируется автоматически)
            
        Returns:
            Tuple[bool, str, Optional[str]]: (успех, сообщение, путь к файлу)
        """
        try:
            # Проверяем существование базы данных
            if not os.path.exists(config.DB_PATH):
                logger.error(f"База данных не найдена: {config.DB_PATH}")
                return False, "❌ База данных не найдена", None
            
            # Генерируем имя файла, если не указано
            if backup_name is None:
                timestamp = datetime.now(UZ_TZ).strftime("%Y-%m-%d_%H-%M-%S")
                backup_name = f"backup_{timestamp}.db"
            elif not backup_name.endswith('.db'):
                backup_name += '.db'
            
            # Полный путь к файлу бэкапа
            backup_path = os.path.join(BACKUP_DIR, backup_name)
            
            # Закрываем все соединения с БД перед копированием
            await BackupManager._close_all_connections()
            
            # Копируем файл
            shutil.copy2(config.DB_PATH, backup_path)
            
            # Проверяем целостность бэкапа
            if not await BackupManager._verify_database(backup_path):
                os.remove(backup_path)
                return False, "❌ Созданный бэкап поврежден", None
            
            logger.info(f"Резервная копия создана: {backup_path}")
            return True, f"✅ Резервная копия создана: {backup_name}", backup_path
            
        except Exception as e:
            logger.exception(f"Ошибка при создании бэкапа: {e}")
            return False, f"❌ Ошибка при создании бэкапа: {str(e)}", None
    
    @staticmethod
    async def _close_all_connections():
        """Закрывает все активные соединения с SQLite"""
        try:
            # Принудительное закрытие всех соединений через aiosqlite
            # (это не идеальное решение, но работает для большинства случаев)
            for conn in aiosqlite._connections:
                try:
                    await conn.close()
                except:
                    pass
        except:
            pass
        
        # Небольшая задержка для гарантии закрытия
        await asyncio.sleep(0.1)
    
    @staticmethod
    async def _verify_database(db_path: str) -> bool:
        """Проверяет целостность базы данных SQLite"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            return result[0] == "ok"
        except:
            return False
    
    @staticmethod
    async def restore_from_backup(backup_path: str) -> Tuple[bool, str]:
        """
        Восстанавливает базу данных из резервной копии.
        
        Args:
            backup_path: Путь к файлу бэкапа
            
        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        try:
            # Проверяем, что файл существует
            if not os.path.exists(backup_path):
                return False, "❌ Файл бэкапа не найден"
            
            # Проверяем, что это корректная SQLite база
            if not await BackupManager._verify_database(backup_path):
                return False, "❌ Файл не является корректной SQLite-базой данных"
            
            # Создаем временную копию текущей базы
            if os.path.exists(config.DB_PATH):
                shutil.copy2(config.DB_PATH, TEMP_BACKUP)
                logger.info(f"Создана временная копия текущей базы: {TEMP_BACKUP}")
            
            # Закрываем все соединения с БД
            await BackupManager._close_all_connections()
            
            # Копируем бэкап на место текущей базы
            shutil.copy2(backup_path, config.DB_PATH)
            logger.info(f"База данных восстановлена из: {backup_path}")
            
            # Проверяем восстановленную базу
            if not await BackupManager._verify_database(config.DB_PATH):
                # Если восстановление не удалось, восстанавливаем временную копию
                if os.path.exists(TEMP_BACKUP):
                    shutil.copy2(TEMP_BACKUP, config.DB_PATH)
                    logger.info("Восстановлена временная копия из-за ошибки проверки")
                return False, "❌ Восстановленная база данных повреждена, выполнена откат"
            
            # Удаляем временную копию после успешного восстановления
            if os.path.exists(TEMP_BACKUP):
                os.remove(TEMP_BACKUP)
                logger.info("Временная копия удалена")
            
            # Переинициализируем соединение с БД
            await db.init_db()
            await db.migrate_if_needed()
            
            return True, "✅ База данных успешно восстановлена"
            
        except Exception as e:
            logger.exception(f"Ошибка при восстановлении: {e}")
            
            # Пытаемся восстановить из временной копии
            if os.path.exists(TEMP_BACKUP):
                try:
                    shutil.copy2(TEMP_BACKUP, config.DB_PATH)
                    logger.info("Восстановлена временная копия после ошибки")
                    return False, f"❌ Ошибка восстановления, выполнена откат: {str(e)}"
                except:
                    pass
            
            return False, f"❌ Критическая ошибка восстановления: {str(e)}"
    
    @staticmethod
    async def list_backups() -> list:
        """Возвращает список всех доступных бэкапов с информацией о них"""
        backups = []
        try:
            for file in os.listdir(BACKUP_DIR):
                if file.endswith('.db'):
                    file_path = os.path.join(BACKUP_DIR, file)
                    stat = os.stat(file_path)
                    size = stat.st_size
                    modified = datetime.fromtimestamp(stat.st_mtime)
                    # Проверяем целостность
                    is_valid = await BackupManager._verify_database(file_path)
                    
                    backups.append({
                        'name': file,
                        'path': file_path,
                        'size': size,
                        'size_mb': size / (1024 * 1024),
                        'modified': modified,
                        'modified_str': modified.strftime("%Y-%m-%d %H:%M:%S"),
                        'is_valid': is_valid
                    })
        except Exception as e:
            logger.exception(f"Ошибка при получении списка бэкапов: {e}")
        
        # Сортируем по дате изменения (новые сверху)
        backups.sort(key=lambda x: x['modified'], reverse=True)
        return backups
    
    @staticmethod
    async def delete_old_backups(days: int = 30):
        """Удаляет старые бэкапы старше указанного количества дней"""
        deleted = []
        try:
            cutoff = datetime.now() - timedelta(days=days)
            for file in os.listdir(BACKUP_DIR):
                if file.endswith('.db'):
                    file_path = os.path.join(BACKUP_DIR, file)
                    stat = os.stat(file_path)
                    modified = datetime.fromtimestamp(stat.st_mtime)
                    
                    if modified < cutoff:
                        os.remove(file_path)
                        deleted.append(file)
                        logger.info(f"Удален старый бэкап: {file}")
        except Exception as e:
            logger.exception(f"Ошибка при удалении старых бэкапов: {e}")
        
        return deleted
    
    @staticmethod
    async def cleanup_temp_files():
        """Удаляет временные файлы"""
        try:
            for temp_file in [TEMP_DB, TEMP_BACKUP]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(f"Удален временный файл: {temp_file}")
        except Exception as e:
            logger.exception(f"Ошибка при очистке временных файлов: {e}")


async def send_backup_to_admin(bot: Bot, backup_path: str, backup_name: str):
    """Отправляет файл бэкапа администратору"""
    try:
        with open(backup_path, 'rb') as f:
            await bot.send_document(
                chat_id=config.ADMIN_CHAT_ID,
                document=types.FSInputFile(backup_path, filename=backup_name),
                caption=f"📦 Резервная копия базы данных\n📅 {datetime.now(UZ_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
            )
        logger.info(f"Бэкап отправлен администратору: {backup_name}")
        return True
    except Exception as e:
        logger.exception(f"Ошибка при отправке бэкапа: {e}")
        return False


async def auto_backup_task(bot: Bot):
    """
    Фоновая задача для автоматического создания бэкапов каждые 7 дней.
    Запускается при старте бота.
    """
    # Очищаем временные файлы при старте
    await BackupManager.cleanup_temp_files()
    
    # Удаляем старые бэкапы (старше 30 дней)
    await BackupManager.delete_old_backups(days=30)
    
    while True:
        try:
            # Ждем 7 дней (604800 секунд)
            await asyncio.sleep(604800)
            
            # Создаем бэкап
            timestamp = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
            backup_name = f"auto_backup_{timestamp}.db"
            
            success, message, backup_path = await BackupManager.create_backup(backup_name)
            
            if success and backup_path:
                # Отправляем бэкап администратору
                await send_backup_to_admin(bot, backup_path, backup_name)
                logger.info(f"Автоматический бэкап создан и отправлен: {backup_name}")
            else:
                logger.error(f"Ошибка автоматического бэкапа: {message}")
                
        except Exception as e:
            logger.exception(f"Ошибка в задаче автоматического бэкапа: {e}")
