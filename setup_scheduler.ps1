
$action  = New-ScheduledTaskAction -Execute "C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe" -Argument "C:\Users\USER\Desktop\01_TRINITY\main.py" -WorkingDirectory "C:\Users\USER\Desktop\01_TRINITY"
$trigger = New-ScheduledTaskTrigger -Daily -At "05:00"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -RunOnlyIfNetworkAvailable $true
Register-ScheduledTask -TaskName "TRINITY_DailyRun" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force
Write-Host "TRINITY 排程任務建立成功！每天 05:00 自動執行"
