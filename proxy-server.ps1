$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http

$targetBase = 'https://studentroadmap-api-m5hqauiyxa-nw.a.run.app'
$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add('http://127.0.0.1:8081/')
$listener.Start()

$httpClientHandler = [System.Net.Http.HttpClientHandler]::new()
$httpClientHandler.AllowAutoRedirect = $true
$client = [System.Net.Http.HttpClient]::new($httpClientHandler)

Write-Host "CORS proxy running on http://127.0.0.1:8081"
Write-Host "Forwarding to $targetBase"

function Add-CorsHeaders($response) {
    $response.Headers['Access-Control-Allow-Origin'] = '*'
    $response.Headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    $response.Headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
}

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        try {
            Add-CorsHeaders $response

            if ($request.HttpMethod -eq 'OPTIONS') {
                $response.StatusCode = 204
                $response.Close()
                continue
            }

            $targetUrl = "$targetBase$($request.RawUrl)"
            $method = [System.Net.Http.HttpMethod]::new($request.HttpMethod)
            $proxyRequest = [System.Net.Http.HttpRequestMessage]::new($method, $targetUrl)

            foreach ($headerKey in $request.Headers.AllKeys) {
                if ($headerKey -in @('Host', 'Content-Length', 'Connection')) { continue }

                $headerValue = $request.Headers[$headerKey]
                $addedToRequest = $proxyRequest.Headers.TryAddWithoutValidation($headerKey, $headerValue)

                if (-not $addedToRequest -and $null -ne $proxyRequest.Content) {
                    $proxyRequest.Content.Headers.TryAddWithoutValidation($headerKey, $headerValue) | Out-Null
                }
            }

            if ($request.HasEntityBody) {
                $reader = [System.IO.BinaryReader]::new($request.InputStream)
                $bodyBytes = $reader.ReadBytes([int]$request.ContentLength64)
                $proxyRequest.Content = [System.Net.Http.ByteArrayContent]::new($bodyBytes)
                if ($request.ContentType) {
                    $proxyRequest.Content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse($request.ContentType)
                }
            }

            $proxyResponse = $client.SendAsync($proxyRequest).GetAwaiter().GetResult()

            $response.StatusCode = [int]$proxyResponse.StatusCode

            foreach ($header in $proxyResponse.Headers) {
                foreach ($value in $header.Value) {
                    try { $response.Headers.Add($header.Key, $value) } catch {}
                }
            }

            if ($proxyResponse.Content) {
                foreach ($header in $proxyResponse.Content.Headers) {
                    foreach ($value in $header.Value) {
                        try { $response.Headers.Add($header.Key, $value) } catch {}
                    }
                }

                $bytes = $proxyResponse.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }

            $response.OutputStream.Flush()
            $response.Close()
        }
        catch {
            try {
                Add-CorsHeaders $response
                $response.StatusCode = 502
                $errorJson = "{`"error`":`"Proxy error`",`"details`":`"$($_.Exception.Message.Replace('"','\"'))`"}"
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorJson)
                $response.ContentType = 'application/json'
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
                $response.Close()
            }
            catch {}
        }
    }
}
finally {
    $listener.Stop()
    $listener.Close()
    $client.Dispose()
}
