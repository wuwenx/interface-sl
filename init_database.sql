-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS `exchange_api` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 使用数据库
USE `exchange_api`;

-- 创建交易所币对信息表
CREATE TABLE IF NOT EXISTS `exchange_symbols` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `exchange` varchar(50) NOT NULL COMMENT '交易所名称',
  `symbol` varchar(50) NOT NULL COMMENT '交易对符号',
  `base_asset` varchar(50) NOT NULL COMMENT '基础资产',
  `quote_asset` varchar(50) NOT NULL COMMENT '计价资产',
  `status` varchar(20) NOT NULL COMMENT '交易状态',
  `type` varchar(20) NOT NULL DEFAULT 'spot' COMMENT '交易对类型：spot(现货) 或 contract(合约)',
  `base_asset_precision` varchar(50) DEFAULT NULL COMMENT '基础资产精度',
  `quote_precision` varchar(50) DEFAULT NULL COMMENT '计价资产精度',
  `min_price` float DEFAULT NULL COMMENT '最小价格',
  `max_price` float DEFAULT NULL COMMENT '最大价格',
  `tick_size` float DEFAULT NULL COMMENT '价格精度',
  `min_qty` float DEFAULT NULL COMMENT '最小数量',
  `max_qty` float DEFAULT NULL COMMENT '最大数量',
  `step_size` float DEFAULT NULL COMMENT '数量精度',
  `raw_data` longtext DEFAULT NULL COMMENT '原始JSON数据',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_exchange_symbol` (`exchange`,`symbol`,`type`),
  KEY `idx_exchange_type` (`exchange`,`type`),
  KEY `idx_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='交易所币对信息表';
