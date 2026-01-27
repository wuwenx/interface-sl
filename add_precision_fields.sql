-- 添加精度字段到现有数据库表
USE `exchange_api`;

-- 添加base_asset_precision字段
ALTER TABLE `exchange_symbols` 
ADD COLUMN `base_asset_precision` varchar(50) DEFAULT NULL COMMENT '基础资产精度' AFTER `type`;

-- 添加quote_precision字段
ALTER TABLE `exchange_symbols` 
ADD COLUMN `quote_precision` varchar(50) DEFAULT NULL COMMENT '计价资产精度' AFTER `base_asset_precision`;
