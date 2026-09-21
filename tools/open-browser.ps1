param([int]$Port=8000,[string]$LoginPath="/frontend/login.html",[string]$Mode="quick")
$t=0; $max=40; $uri="http://127.0.0.1:$Port/health"; $local="http://127.0.0.1:$Port$LoginPath"; $pub="https://service.reneepsl.my.id$LoginPath"
while($t -lt $max){
  try{ $r=Invoke-WebRequest -Uri $uri -TimeoutSec 1 -UseBasicParsing; if($r.StatusCode -eq 200){ Start-Process $local; if($Mode -eq "named"){ Start-Process $pub }; exit 0 } }catch{}
  Start-Sleep -Milliseconds 300; $t++
}
Start-Process $local; if($Mode -eq "named"){ Start-Process $pub }
