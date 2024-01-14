Output decrypt.gif

Require ssh-to-age
Require sops

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 300
Set Margin 0
Set BorderRadius 0
Set TypingSpeed 50ms
Set WindowBarSize 0

Type "export SOPS_AGE_KEY=$(ssh-to-age -private-key < ~/.ssh/id_ed25519)"
Enter
Sleep 4s
Type "sops -d keys.enc.yaml"
Enter
Sleep 10s
