#!/bin/sh

# Select executable based on architecture
if [ "$TARGETARCH" = "arm64" ] || [ "$TARGETARCH" = "arm" ]; then
  SERVER_BINARY="mono ./TerrariaServer.exe"
else
  SERVER_BINARY="./TerrariaServer"
fi

WORLD_PATH="${TERRARIA_SERVER_PATH}/${DEFAULT_TERRARIA_SERVER_PATH}/Worlds/${WORLD_FILENAME}"

# Print server information
printf "Server binary : %s\n" "$SERVER_BINARY"
printf "Architecture  : %s\n" "$TARGETARCH"
printf "World file    : %s\n" "$WORLD_PATH"
printf "Log path      : %s\n" "$LOG_PATH"
printf "Config file   : %s\n" "${CONFIG_PATH}/${CONFIG_FILENAME}"

# Check if the config file is the default by comparing MD5
DEFAULT_MD5=$(cat "${CONFIG_PATH}/default-serverconfig.md5")
CURRENT_MD5=$(md5sum "${CONFIG_PATH}/${CONFIG_FILENAME}" | cut -d' ' -f1)

if [ "$DEFAULT_MD5" = "$CURRENT_MD5" ]; then
  printf "Warning: Using default server configuration (MD5: %s)\n" "$DEFAULT_MD5"
else
  printf "Using non-default server configuration (%s)\n" "$CONFIG_PATH/$CONFIG_FILENAME"
fi

# Check if password is empty in any config
if grep -q "^password=$\|^password=\"\"$" "${CONFIG_PATH}/${CONFIG_FILENAME}"; then
  printf "Warning: Server password is not set in your configuration file!\n"
fi

if [ $# -gt 0 ]; then
  echo "Running terraria-server with arguments: %s\n" "$@"
fi  

if [ -f "$WORLD_PATH" ]; then
  # Load existing world
  printf "Loading existing world: %s\n" "$WORLD_PATH"
  $SERVER_BINARY -config "${CONFIG_PATH}/${CONFIG_FILENAME}" -logpath "$LOG_PATH" -world "$WORLD_PATH" "$@"

elif [ "$TEST_MODE" = "true" ]; then

  RANDOM_SEED=$(od -A n -t d -N 3 /dev/urandom | tr -d ' ')
  printf "No existing world file specified.\n"
  printf "Creating new world with default name and seed %s\n." "$RANDOM_SEED"
  $SERVER_BINARY -config "$CONFIG_PATH/$CONFIG_FILENAME" -logpath "$LOG_PATH" -world "$WORLD_PATH" -autocreate 1 -worldname "Terraria" -seed "$RANDOM_SEED" "$@"

else
  printf "Error: A volume with a World file must be mounted to '$WORLD_PATH' to persist your progress. Exiting."
  exit 1
fi
