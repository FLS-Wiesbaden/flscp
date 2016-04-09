<?php

/**
 * FLS Password Driver
 * for Roundcube Password plugin
 *
 * @version 0.1
 * @author Website-Team
 */

class rcube_fls_password
{
    function save($currpass, $newpass)
    {
        $username = escapeshellcmd($_SESSION['username']);
        $sockpath = rcmail::get_instance()->config->get('password_fls_sock','/var/run/flscp.sock');

        // now try to connect to unix socket (/var/run/flscp.sock)
        $sock = socket_create(AF_UNIX, SOCK_STREAM, 0);
        if ($sock === false) {
            syslog(LOG_ERROR, 'Could not create socket');
            raise_error(array(
                'code' => 500,
                'type' => 'php',
                'file' => __FILE__, 'line' => __LINE__,
                'message' => 'Could not connect to flscp server via socket.'
            ), true, false);
            return PASSWORD_ERROR;
        }

        socket_set_block($sock);
        $fh = socket_connect($sock, $sockpath);
        if ($fh === true) {
            $data = base64_encode(base64_encode($username . ' ' . $newpass) . ';' . $currpass);
            $msg = 'chgpwd;' . $data;
            $d = socket_write($sock, $msg);
            if ($d !== false) {
                // read single line
                $buf = socket_read($sock, 2048);
                if ($buf !== false) {
                    list($code, $msg) = explode(' - ', $buf);
                    if ($code == 200) {
                        return PASSWORD_SUCCESS;
                    }
                }
            }
        }

        return PASSWORD_ERROR;
    }
}

?>