Output setup.gif

Require github-to-sops
Require yq
Require git

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 600
Set Margin 0
# Set TypingSpeed 50ms

Type "yq . < keys.unsafe.yaml"
Enter
Sleep 4s
Type "github-to-sops --github-url https://github.com/tarasglek/chatcraft.org --key-types ssh-ed25519 --format sops > .sops.yaml"
Enter
Sleep 10s
Type "yq . < .sops.yaml"
Enter
Sleep 10s
Type "sops -e keys.unsafe.yaml > keys.enc.yaml"
Enter
Sleep 4s
Type "head -n 15 keys.enc.yaml | yq ."
Enter
Sleep 10s
Type "git add keys.enc.yaml"
Enter
Sleep 10s



