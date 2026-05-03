param(
    [ValidateSet('master', 'worker', 'all')]
    [string]$Role = 'all'
)

$ErrorActionPreference = 'Stop'

function Ensure-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script from an elevated PowerShell session (Run as Administrator).'
    }
}

function Add-PortRules {
    param(
        [string]$GroupName,
        [int[]]$Ports,
        [string]$DescriptionPrefix
    )

    foreach ($port in $Ports) {
        $ruleName = "${GroupName} TCP $port"
        $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

        if ($existing) {
            Write-Host "Skipping existing rule: $ruleName"
            continue
        }

        New-NetFirewallRule `
            -DisplayName $ruleName `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $port `
            -Profile Any `
            -Group $GroupName `
            -Description "$DescriptionPrefix TCP port $port"

        Write-Host "Created rule: $ruleName"
    }
}

Ensure-Admin

$masterPorts = @(9000, 9870, 8088, 8030, 8031, 8032, 8033, 9868, 18080)
$workerPorts = @(9864, 9866, 9867, 8042)

Write-Host '========================================'
Write-Host 'Hadoop / Spark Firewall Setup'
Write-Host '========================================'
Write-Host "Role: $Role"
Write-Host ''

switch ($Role) {
    'master' {
        Add-PortRules -GroupName 'MMDS Hadoop Spark Master' -Ports $masterPorts -DescriptionPrefix 'Hadoop/Spark master'
    }
    'worker' {
        Add-PortRules -GroupName 'MMDS Hadoop Spark Worker' -Ports $workerPorts -DescriptionPrefix 'Hadoop/Spark worker'
    }
    'all' {
        Add-PortRules -GroupName 'MMDS Hadoop Spark Master' -Ports $masterPorts -DescriptionPrefix 'Hadoop/Spark master'
        Add-PortRules -GroupName 'MMDS Hadoop Spark Worker' -Ports $workerPorts -DescriptionPrefix 'Hadoop/Spark worker'
    }
}

Write-Host ''
Write-Host 'Done.'
Write-Host 'Verify rules with:'
Write-Host '  Get-NetFirewallRule -Group "MMDS Hadoop Spark Master"'
Write-Host '  Get-NetFirewallRule -Group "MMDS Hadoop Spark Worker"'