Output updatekeys.gif

Require ssh-to-age
Require sops
Require github-to-sops

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 600
Set Margin 0
Set BorderRadius 0
Set WindowBarSize 0


Type "github-to-sops --inplace-edit .sops.yaml --github-users tarasglek,rjwignar"
Enter
Sleep 4s
Type "yq . < .sops.yaml"
Enter
Sleep 10s
Type "export SOPS_AGE_KEY=$(ssh-to-age -private-key < ~/.ssh/id_ed25519)"
Enter
Sleep 4s
Type "sops updatekeys -y keys.enc.yaml"
Enter
Sleep 10s
