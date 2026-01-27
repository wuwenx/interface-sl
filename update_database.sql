-- 更新数据库表结构，将raw_data字段改为LONGTEXT
USE `exchange_api`;

-- 修改raw_data字段类型为LONGTEXT
ALTER TABLE `exchange_symbols` 
MODIFY COLUMN `raw_data` longtext DEFAULT NULL COMMENT '原始JSON数据';
