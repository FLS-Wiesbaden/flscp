<?php

/**
 * FLS Password Driver
 *
 * @version 0.1
 * @author Website-Team
 */

class rcube_fls_password
{
    function save($currpass, $newpass)
    {
	$username = escapeshellcmd($_SESSION['username']);
        $sock = rcmail::get_instance()->config->get('password_fls_sock','/var/run/flscp.sock');

	// now try to connect to unix socket (/var/run/flscp.sock)
	$sock = socket_create(AF_UNIX, SOCK_STREAM, 0);
	if ($sock === false) {
            raise_error(array(
                'code' => 500,
                'type' => 'php',
                'file' => __FILE__, 'line' => __LINE__,
                'message' => 'Could not connect to flscp server via socket.'
	    ), true, false);
	    return PASSWORD_ERROR;
	}

	$fh = socket_connect($sock, $sock);
	if ($fh === true) {
	    $data = base64_encode($username . ' ' . $newpass);
	    $msg = 'chgpwd;' . $data;
	    $d = socket_send($sock, $msg, strlen($msg));
	    if ($d !== false) {
		// read single line
		$buf = false;
		$bytes = socket_recv($sock, $buf, 2048);
		if ($bytes !== false) {
		    list($code, $msg) = $buf;
		    if ($code == 200) {
			return PASSWORD_SUCCESS;
		    }
		}
	    }
	}

        return PASSWORD_ERROR;
    }
}
