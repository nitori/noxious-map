<?php

$vars = [
    'METADATA_MTIME' => filemtime(__DIR__ . '/js/metadata.json'),
    'SCRIPT_MTIME' => filemtime(__DIR__ . '/js/script.js'),
];

$html = file_get_contents(__DIR__ . '/start.html');
$html = preg_replace_callback('/%%(\w+?)%%/', function ($match) use ($vars) {
    return $vars[$match[1]] ?? '';
}, $html);

echo $html;
