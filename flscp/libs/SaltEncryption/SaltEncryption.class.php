<?php
/**
 * SaltEncryption - Improved Hash Algorithm (IHA),
 * Generates a strong hash value from a weak password
 * Original written 2007 by Nils Reimers (php-einfach.de)
 *
 * PHP Version 5.3
 *
 * @package   FLS
 * @author    Website-Team <website-team@fls-wiesbaden.de>
 * @author    Nils Reimers <webmaster@php-einfach.de>
 * @copyright 2011-2012 Website-Team <website-team@fls-wiesbaden.de>
 * @copyright 2007 Nils Reimers <webmaster@php-einfach.de>
 * @license   LGPL2.1+ http://www.gnu.org/licenses/lgpl.html
 * @link      https://trac.fls-wiesbaden.de/browse/flshp/trunk/inc/SaltEncryption.class.php
 */

// maybe includes in future.

/**
 * SaltEncryption - Improved Hash Algorithm (IHA),
 * Generates a strong hash value from a weak password
 * Original written 2007 by Nils Reimers (php-einfach.de)
 *
 * PHP Version 5.3
 *
 * @package   FLS
 * @author    Website-Team <website-team@fls-wiesbaden.de>
 * @author    Nils Reimers <webmaster@php-einfach.de>
 * @copyright 2011-2012 Website-Team <website-team@fls-wiesbaden.de>
 * @copyright 2007 Nils Reimers <webmaster@php-einfach.de>
 * @license   LGPL2.1+ http://www.gnu.org/licenses/lgpl.html
 * @link      https://trac.fls-wiesbaden.de/browse/flshp/trunk/inc/SaltEncryption.class.php
 */
class SaltEncryption {

    /**
     * Number of rounds
     * A higher number of rounds increase the security,
     * but it take more time for the calculation of a hash
     *
     * @var integer Number of rounds
     */
    private $rounds = 10000;

    /**
     * Using SHA1 or MD5
     * If $sha1 is true, then SHA1 would be used instead of MD5
     * 
     * @var boolean true => use SHA1 | false => use MD5
     */
    private $sha1 = True;

    /**
     * Length of the salt
     * The salt is the part from the start to the semicolon (;) of the output
     * Its needed to prevent a dictionary attack
     *
     * @var integer
     */
    private $saltLng = 16;

    /**
     * A secret password
     * When $password has a value, only persons who know the password
     * can generate valid password hashs.
     * When the password get lost, existing password hashs cannot be verify anoymore
     * The constructor tries to get it via $conf
     *
     * @var string
     */
    private $password = "";

    /**
     * SaltEncryption
     * Constructor
     *
     * Here you can give me a password or i will try via Configuration.
     *
     * @param string $password a Password for hashing.
     */
    function SaltEncryption($password = '') {
        if (!empty($password)) {
            $this->password = $password;
        } else if (class_exists('\FLS\Lib\Configuration\Configuration')) {
            $conf = \FLS\Lib\Configuration\Configuration::getInstance();
            if ($conf != null) {
                $password = $conf->datenbank->hashPassword->value;
                if ($password != null) {
                    $this->password = $password;
                }
            }
        }
    }

    /**
     * The Hash-Function
     * This function generates and returns a more secure hash of a password.
     * If $salt has no value, a random $salt would be generated.
     *
     * @param string $pwd  Password which should be hashed
     * @param string $salt The Salt Hash for generating the password hash
     *
     * @return string The hash: header;salt;key
     */
    public function hash($pwd, $salt = null) {
        if (is_null($salt)) {
            // We have no $salt, so we generate it.
            $salt = $this->generateSalt();
        }

        // we have to generate an header
        $header = $this->generateHeader();
        $key = $salt . $pwd . $this->password;

        /* We can only use $sha1 if
         * (a) we should use it
         * (b) the function ("sha1") exist
         */
        if ($this->sha1 == true AND function_exists("sha1")) {
            $key = sha1($key);
        } else {
            $key = md5($key);
        }

        // We have to pack and strech it.
        $key = base64_encode(pack("H*", $this->keyStretching($key)));

        return $header . ";" . $salt . ';' . $key;
    }

    /**
     * Verifies if a password is valid
     * This function checks, if the value of $pwd belongs to the value of $hash
     * $hash could come from a database or something else
     *
     * @param string $pwd  the Password
     * @param string $hash a Salt-Hash of a password. Hopefully the hash of the $pwd ;-)
     *
     * @return boolean true if the password is valid, else: false
     */
    public function compare($pwd, $hash) {
        $t = explode(';', $hash);

        if (count($t) == 3) {
            list($header, $salt, $value) = $t;
            $header = base64_decode($header);
            $rounds = ord($header{1}) << 16 | ord($header{2}) << 8 | ord($header{3});
            $flag = ord($header{0});

            //Save the settings
            $tmpRounds = $this->rounds;
            $tmpSHA1 = $this->sha1;

            $this->rounds = $rounds;
            $this->sha1 = ((($flag & 0x80) >> 7) == 1);

            $equal = ($this->hash($pwd, $salt) == $hash);

            //Restore the settings
            $this->rounds = $tmpRounds;
            $this->sha1 = $tmpSHA1;
        } else {
            $equal = false;
        }

        return $equal;
    }

    /**
     * Okay. Maybe this is useless. But hey: its a nice feature :D
     * This functions prints out informationen about this object (not the class itself directly)
     * At the second point, it makes a benchmark.
     *
     * @return void
     */
    public function info() {
        echo "<b>Improved Hash Algorithm</b>\n";
        echo "Version: Rolling Release ;-) \n";
        echo "Algorithm: " . (($this->sha1 == true AND function_exists("sha1")) ? "SHA1" : "MD5") . "\n";
        echo "Rounds: " . $this->rounds . "\n";
        echo "Salt-Length: " . $this->saltLng . "\n";
        echo "Password: " . ((empty($this->password)) ? "No" : "Yes") . "\n";

        // Start Benchmark
        $this->benchmark();

        echo "\n\n";
    }

    /**
     * We want to test the class. Here we go with a simple benchmark.
     *
     * @param integer $num How often should be tested?
     *
     * @return void
     */
    public function benchmark($num=1000) {
        echo "Generating $num hashs: \n";

        $start = (double) microtime() + time();

        for ($i = 0; $i < $num; $i++) {
            $this->hash("Benchmark");
        }

        $ende = (double) microtime() + time();
        $diff = round($ende - $start, 4);

        echo "Generated in " . $diff . " seconds; " . ($diff / $num) . " per hash";
    }


    /**
     * This method strechs the key (hash of password)
     * This is useful so that its more difficult to crack
     * the password.
     *
     * @param string $key the passwordhash
     *
     * @return string the streched key.
     *
     * @access private
     */
    private function keyStretching($key) {
        if ($this->sha1 == true AND function_exists("sha1")) {
            for ($i = 0; $i < $this->rounds; ++$i) {
                $key = sha1($key);
            }
        } else {
            for ($i = 0; $i < $this->rounds; ++$i) {
                $key = md5($key);
            }
        }

        return $key;
    }

    /**
     * This method generate a random salt, based on the current time
     *
     * @return string Salt (md5 hash) 
     *
     * @access private
     */
    private function generateSalt() {
        $salt = base64_encode(pack("H*", md5(microtime())));
        return substr($salt, 0, $this->saltLng);
    }

    /**
     * Generates a header for the hash, so you can identify which settings was used to
     * generate the hash.
     *
     * @return string the Header.
     *
     * @access private
     */
    private function generateHeader() {
        $rounds = $this->rounds;
        $flag = (($this->sha1 == true AND function_exists("sha1")) ? 1 : 0) << 7;


        return substr(base64_encode(pack("N*", $rounds | $flag << 24)), 0, 6);
    }

}

?>
