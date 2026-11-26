#!/bin/sh
set -eu

ipfs config Pubsub.Enabled --json true
ipfs config Ipns.UsePubsub --json true
ipfs config AutoTLS.Enabled --json false
ipfs config Addresses.AppendAnnounce --json "[\"$IPFS_ANNOUNCE\"]"
