#!/usr/bin/env php
<?php
require_once 'SaltEncryption.class.php';

$pw = trim(fgets(STDIN));
$hash = trim(fgets(STDIN));
$iha = new SaltEncryption();
$hashPw = $iha->compare($pw, $hash);

fputs(STDOUT, $hashPw ? 'yes' : 'no');
?>
