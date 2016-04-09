--
-- Table structure for table `mail_users`
--
ALTER TABLE `mail_users` 
	ADD COLUMN `encryption` tinyint(1) unsigned NOT NULL DEFAULT '0', 
	ADD COLUMN `public_key` text CHARACTER SET utf8 NOT NULL DEFAULT '', 
	ADD COLUMN `private_key` text CHARACTER SET utf8 NOT NULL DEFAULT '', 
	ADD COLUMN `private_key_salt` varchar(50) CHARACTER SET utf8 NOT NULL DEFAULT '', 
	ADD COLUMN `private_key_iterations` tinyint(2) unsigned NOT NULL DEFAULT '10' AFTER `authvalid`;

ALTER TABLE `mail_users` 
	ADD COLUMN `filter_postgrey` tinyint(1) unsigned NOT NULL DEFAULT '1',
	ADD COLUMN `filter_virus` tinyint(1) unsigned NOT NULL DEFAULT '1',
	ADD COLUMN `filter_spam` tinyint(1) unsigned NOT NULL DEFAULT '1' AFTER `status`;