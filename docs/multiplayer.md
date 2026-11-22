# Playing online with friends

One player hosts and the others join with an invite code. No outside server or account is needed: the host's PC runs the game's online server and passes all game traffic between players. Only the host needs an open port.

Everyone needs the same release of the port (v0.1.3 or later) and their own set-up copy of the game.

## Host a game

1. Open the launcher and go to the Online tab.
2. Type a name in Your name. It is your online ID, and the name your game is listed under in Find games on my network.
3. Leave "Open the port on my router" ticked. The launcher asks your router to open the port (UPnP or NAT-PMP).
4. Press Host a game. The first start takes about a minute. When the server is ready, the tab shows an invite code such as `R2M0-255Y-FPT7-WP1X`.
5. Press Copy and send the code to your friends.
6. Press Play, then in the game pick Online, then Open Course.

Keep the launcher open while you host: closing it stops the server. Press Stop hosting when you are done.

The first time, Windows may ask whether Python may use the network. Allow it, or your friends can't connect.

## Join a game

1. Open the launcher and go to the Online tab.
2. Type a name in Your name. It is your online ID.
3. Paste the host's invite code into Join.
4. Press Play, then in the game pick Online, then Open Course.

On the same home network, Find games on my network lists the host, so you don't need the code.

To play offline again, clear the Join box.

## Which code to send

The main invite code works over the internet. Below it, the Online tab lists codes under "Same network or VPN":

- **home network:** for friends on the same Wi-Fi or router as you.
- **a VPN adapter** (Tailscale, ZeroTier and others): for friends on the same VPN. Use this when your router can't open the port.

The invite code holds your public IP address. Send it only to people you want to play with.

## When friends can't connect

The Online tab says what went wrong. Work through these in order:

1. **The router didn't open the port.** Some routers have UPnP turned off. Turn UPnP on in your router's settings, or forward TCP port 48765 to the host's PC by hand. If you changed the Port box, forward that port instead.
2. **The firewall blocked it.** Allow Python through Windows Firewall for private and public networks, or answer Allow when Windows asks.
3. **Your internet provider shares one public address among many homes (CGNAT).** Port forwarding can't work then. Have everyone join one VPN such as Tailscale and use the VPN code from the Online tab.
4. **The code was copied wrong.** A valid code is four groups of four letters and digits. Copy it again with the Copy button.

Friends who join never need to open a port.

## Host without playing

To run the server on a PC that won't play, unpack the release there, set up the game files once, and run `tools\server\host-online.cmd`. It opens the router port and prints the invite codes. Close the window to stop it.

## What works and what doesn't yet

- Tested: two copies of the game on one PC joined by invite code through a real router, including with 80 ms of added lag. Both players meet in the same Open Course lobby, each with their own golfer and name tag.
- Not tested yet: players in two different homes, and a full round played together. If you try it, please open an issue and say how it went.
- The name tag over each golfer is that golfer's name from the player's save, not the launcher's Your name.
- Online play uses the game's own online modes. Sony's servers are not contacted, and no PSN account is used.
