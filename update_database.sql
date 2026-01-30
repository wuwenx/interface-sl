-- 更新数据库表结构，将raw_data字段改为LONGTEXT
USE `exchange_api`;

-- 修改raw_data字段类型为LONGTEXT
ALTER TABLE `exchange_symbols` 
MODIFY COLUMN `raw_data` longtext DEFAULT NULL COMMENT '原始JSON数据';

-- 新闻快讯：增加中文翻译字段（表已存在时执行一次；若报 duplicate column 说明已加过可忽略）
ALTER TABLE `news_articles` 
ADD COLUMN `title_zh` varchar(512) DEFAULT NULL COMMENT '标题中文',
ADD COLUMN `summary_zh` text DEFAULT NULL COMMENT '摘要中文',
ADD COLUMN `content_zh` longtext DEFAULT NULL COMMENT '正文中文';
