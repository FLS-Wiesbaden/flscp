#!/usr/bin/env php
<?php
require_once 'SaltEncryption.class.php';

$pw = trim(fgets(STDIN));
$iha = new SaltEncryption();
$hashPw = $iha->hash($pw);

fputs(STDOUT, $hashPw);
?>
