-- MySQL dump 10.15  Distrib 10.0.23-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: localhost    Database: flscp
-- ------------------------------------------------------
-- Server version	10.0.23-MariaDB-0+deb8u1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `dns`
--

DROP TABLE IF EXISTS `dns`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `dns` (
  `dns_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `domain_id` int(10) unsigned NOT NULL,
  `dns_key` varchar(200) NOT NULL DEFAULT '',
  `dns_type` enum('SOA','NS','MX','A','AAAA','CNAME','TXT','SPF','SRV') CHARACTER SET utf8 COLLATE utf8_general_mysql500_ci NOT NULL DEFAULT 'A',
  `dns_value` tinytext NOT NULL,
  `dns_prio` tinyint(3) unsigned DEFAULT '0',
  `dns_weight` smallint(5) unsigned NOT NULL DEFAULT '0',
  `dns_port` smallint(5) unsigned NOT NULL DEFAULT '0',
  `dns_admin` varchar(250) DEFAULT NULL,
  `dns_refresh` smallint(6) NOT NULL DEFAULT '7200',
  `dns_retry` int(10) unsigned NOT NULL DEFAULT '1800',
  `dns_expire` int(10) unsigned NOT NULL DEFAULT '1209600',
  `dns_ttl` int(10) unsigned NOT NULL DEFAULT '3600',
  `status` varchar(120) NOT NULL DEFAULT 'create',
  PRIMARY KEY (`dns_id`),
  KEY `domain` (`domain_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dns`
--

LOCK TABLES `dns` WRITE;
/*!40000 ALTER TABLE `dns` DISABLE KEYS */;
/*!40000 ALTER TABLE `dns` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `domain`
--

DROP TABLE IF EXISTS `domain`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `domain` (
  `domain_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `domain_parent` int(10) unsigned DEFAULT NULL,
  `domain_name` varchar(200) CHARACTER SET utf8 NOT NULL,
  `ipv6` varchar(40) CHARACTER SET utf8 NOT NULL,
  `ipv4` varchar(15) CHARACTER SET utf8 NOT NULL,
  `domain_gid` int(10) unsigned NOT NULL DEFAULT '0',
  `domain_uid` int(10) unsigned NOT NULL DEFAULT '0',
  `domain_srvpath` varchar(160) COLLATE utf8_unicode_ci NOT NULL DEFAULT '',
  `domain_created` int(10) unsigned NOT NULL DEFAULT '0',
  `domain_last_modified` int(10) unsigned NOT NULL DEFAULT '0',
  `domain_status` varchar(10) CHARACTER SET utf8 NOT NULL DEFAULT 'change',
  PRIMARY KEY (`domain_id`),
  UNIQUE KEY `domain_name` (`domain_name`),
  KEY `fk_domain_domain1_idx` (`domain_parent`),
  CONSTRAINT `fk_domain_domain1` FOREIGN KEY (`domain_parent`) REFERENCES `domain` (`domain_id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `domain`
--

LOCK TABLES `domain` WRITE;
/*!40000 ALTER TABLE `domain` DISABLE KEYS */;
/*!40000 ALTER TABLE `domain` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `domain_aliasses`
--

DROP TABLE IF EXISTS `domain_aliasses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `domain_aliasses` (
  `alias_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `domain_id` int(10) unsigned DEFAULT NULL,
  `alias_name` varchar(200) CHARACTER SET utf8 DEFAULT NULL,
  `alias_status` varchar(255) CHARACTER SET utf8 DEFAULT NULL,
  `alias_mount` varchar(200) CHARACTER SET utf8 DEFAULT NULL,
  `alias_ip_id` int(10) unsigned DEFAULT NULL,
  `url_forward` varchar(200) CHARACTER SET utf8 DEFAULT NULL,
  PRIMARY KEY (`alias_id`),
  KEY `domain_id` (`domain_id`),
  CONSTRAINT `fk_domain_aliasses_domain` FOREIGN KEY (`domain_id`) REFERENCES `domain` (`domain_id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `domain_aliasses`
--

LOCK TABLES `domain_aliasses` WRITE;
/*!40000 ALTER TABLE `domain_aliasses` DISABLE KEYS */;
/*!40000 ALTER TABLE `domain_aliasses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mail_users`
--

DROP TABLE IF EXISTS `mail_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `mail_users` (
  `mail_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `mail_acc` text CHARACTER SET utf8,
  `mail_pass` varchar(150) CHARACTER SET utf8 DEFAULT NULL,
  `mail_forward` text CHARACTER SET utf8,
  `domain_id` int(10) unsigned DEFAULT NULL,
  `mail_type` varchar(30) CHARACTER SET utf8 DEFAULT NULL,
  `sub_id` int(10) unsigned DEFAULT NULL,
  `status` varchar(255) CHARACTER SET utf8 DEFAULT NULL,
  `filter_postgrey` tinyint(1) unsigned NOT NULL DEFAULT '1',
  `filter_virus` tinyint(1) unsigned NOT NULL DEFAULT '1',
  `filter_spam` tinyint(1) unsigned NOT NULL DEFAULT '1',
  `whitelist` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `quota` int(10) DEFAULT '104857600',
  `mail_addr` varchar(254) CHARACTER SET utf8 DEFAULT NULL,
  `alternative_addr` varchar(254) CHARACTER SET utf8 DEFAULT NULL,
  `alias` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `authcode` varchar(32) COLLATE utf8_unicode_ci DEFAULT NULL,
  `authvalid` datetime DEFAULT NULL,
  `encryption` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `public_key` text CHARACTER SET utf8 NOT NULL DEFAULT '',
  `private_key` text CHARACTER SET utf8 NOT NULL DEFAULT '',
  `private_key_salt` varchar(50) CHARACTER SET utf8 NOT NULL DEFAULT '',
  `private_key_iterations` tinyint(2) unsigned NOT NULL DEFAULT '10',
  `enabled` tinyint(1) unsigned NOT NULL DEFAULT '1',
  PRIMARY KEY (`mail_id`),
  KEY `domain_id` (`domain_id`),
  CONSTRAINT `fk_mail_users_domain1` FOREIGN KEY (`domain_id`) REFERENCES `domain` (`domain_id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mail_users`
--

LOCK TABLES `mail_users` WRITE;
/*!40000 ALTER TABLE `mail_users` DISABLE KEYS */;
/*!40000 ALTER TABLE `mail_users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `quota_dovecot`
--

DROP TABLE IF EXISTS `quota_dovecot`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `quota_dovecot` (
  `username` varchar(100) CHARACTER SET utf8 NOT NULL,
  `bytes` bigint(20) NOT NULL DEFAULT '0',
  `messages` int(11) NOT NULL DEFAULT '0',
  PRIMARY KEY (`username`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `quota_dovecot`
--

LOCK TABLES `quota_dovecot` WRITE;
/*!40000 ALTER TABLE `quota_dovecot` DISABLE KEYS */;
/*!40000 ALTER TABLE `quota_dovecot` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2016-04-03 15:08:53
