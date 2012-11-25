<?php
require 'SaltEncryption.class.php';

$salt = new SaltEncryption();
switch ($argv[1]) {
    case 'hash':
        echo $salt->hash($argv[2]);
        break;
}
?>
