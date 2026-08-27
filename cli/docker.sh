#######################################
# Checks if the container scraper is running
# Arguments:
#   $1: node_id
# Returns:
#   0 on success
#######################################
docker::status() {
    local node_id=$1

    echo "$node_id"

}


#######################################
# Restarts the containers
# Arguments:
#   $1: node_id
# Returns:
#   0 on success
#######################################
docker::restart() {
    local node_id=$1

    if [[ "$node_id" == "1" ]]; then
        cd "$SCRIPT_DIR"
        export USER_UID=$(id -u)
        export USER_GID=$(id -g)
        docker compose -f scraper/docker-compose.yml down
        docker compose -f scraper/docker-compose.yml --env-file .env --env-file config.env up --build -d
        docker compose -f broker/docker-compose.yml down
        docker compose -f broker/docker-compose.yml --env-file .env --env-file config.env up --build -d
    else
        echob "NOT IMPLEMENTED FOR OTHER THAN NODE_ID=1"
        return $EXIT_CODE_NOT_IMPLEMENTED
    fi
    # TODO (ahoone): implementing for the proxies
}


#######################################
# Starts the test suite
# Arguments:
#   None
# Returns:
#   0 on success
#######################################
docker::tests() {
    cd "$SCRIPT_DIR"
    docker compose -f tests/docker-compose.yml --env-file .env --env-file config.env up --build -d
    echob "-> docker logs tests"
}
