if [[ -n "$TERM" ]]; then
    FONT_BOLD=$(tput bold)
    FONT_NORMAL=$(tput sgr0)
else
    FONT_BOLD=""
    FONT_NORMAL=""
fi

DEFAULT_WIDTH=9999
DEFAULT_HEIGHT=9999


get_terminal_width() {
    if [[ -n "$TERM" ]]; then
        tput cols
    else
        echo $DEFAULT_WIDTH
    fi
}

get_terminal_height() {
    if [[ -n "$TERM" ]]; then
        tput lines
    else
        echo $DEFAULT_HEIGHT
    fi
}


declare -A TABULAR_STYLE_DEFAULT=(
    [VRTCL_DIVIDER]="│"
    [HRZTL_DIVIDER]="─"
    [INTER_DIVIDER]="┼"
)
declare -A TABULAR_STYLE_EMPTY=(
    [VRTCL_DIVIDER]=""
    [HRZTL_DIVIDER]=""
    [INTER_DIVIDER]=""
)



#######################################
# Put inserted sequence in bold
# Globals:
#   None
# Arguments:
#   $1: string
# Outputs:
#   String to stdout
# Returns:
#   0 on success
#######################################
echob() {
    local sequence="$*"
    printf "%s%b%s\n" "$FONT_BOLD" "$sequence" "$FONT_NORMAL"
}


#######################################
# Echo the sequence dropping the ANSI escape codes with a regex
# Globals:
#   None
# Arguments:
#   $*: string
# Outputs:
#   String wihtout ANSI espace codes to stdout
# Returns:
#   0 on success
#######################################
clean() {
    local sequence=$*
    echo -n "$sequence" | sed -E 's/\x1B\[[0-9;]*[a-zA-Z]//g; s/\x1B\([AB012]//g'
}


#######################################
# Get the *displayed* string length
# Globals:
#   None
# Arguments:
#   $*: string
# Outputs:
#   Length to stdout
# Returns:
#   0 on success
#######################################
len() {
    local sequence=$*
    local clear=$(clean "$sequence")
    echo "${#clear}"
}


#######################################
# Arguments:
#   $1: string
#   $2: times
# Outputs:
#   String to stdout
# Returns:
#   0 on success
#######################################
function repeat_string() {
    local -r string="${1}"
    local -r times="${2}"

    if [[ "${string}" != '' && "${times}" =~ ^[1-9][0-9]*$ ]]; then
        local -r result="$(printf "%${times}s")"
        echo -e "${result// /${string}}"
    fi
}


#######################################
# Draw a box around the provided content
# Globals:
#   None
# Arguments:
#   stdin: content to be boxed via pipe
# Outputs:
#   Boxed content to stdout
# Returns:
#   0 on success
#   1 on terminal screen too tiny
#######################################
draw_box() {
    local content=$(cat)

    # Find the longest line
    local max_width=0
    while IFS= read -r line; do
        local width=$(len "$line")
        ((width > max_width)) && max_width=$width
    done <<< "$content"

    local line width padding
    # if (( $(get_terminal_width) >= max_width + 2 )); then
        # Top border
        printf "┌"
        printf "─%.0s" $(seq 1 $max_width)
        printf "┒\n"

        # Content with side borders
        while IFS= read -r line; do
            local width=$(len "$line")
            local padding=$((max_width - width))
            printf "│%s%*s┃\n" "$line" "$padding"
        done <<< "$content"

        # Bottom border
        printf "┕"
        printf "━%.0s" $(seq 1 $max_width)
        printf "┛\n"
    #else
    #    echob your terminal screen is too tiny for the box!!! >&2
    #    return 1
    #fi
}


#######################################
# Echo per column the field repeated X times
# Globals:
#   None
# Arguments:
#   $1: array of the sizes
#   $2: field to repeat
# Outputs:
#   Repetition lines to stdout
# Returns:
#   0 on success
#######################################
_repeat_thrut_cols() {
    local -n integer_array=$1
    local field=$2

    for count in "${integer_array[@]}"; do
        local _repeat_tabulared=""
        for (( i=0; i<count; i++ )); do
            _repeat_tabulared+="$field"
        done
        echo "$_repeat_tabulared"
    done
}


#######################################
# Format the row from width with the input divider
# Globals:
#   None
# Arguments:
#   $1: array of the sizes
#   $2: array of the values
#   $3: divider
# Outputs:
#   Formatted row to stdout
# Returns:
#   0 on success
#   1 on too large string
#######################################
_get_row_format() {
    # here we cannot use the same variable name as in the draw function
    # (see https://mywiki.wooledge.org/BashFAQ/048#line-120)
    local -n _column_size_array=$1
    local -n _value_array=$2
    local divider=$3

    local format=""
    for (( i=0; i<${#_column_size_array[@]}; i++ )); do
        size=${_column_size_array[i]}
        label=${_value_array[i]}
        label_length=$(len "$label")
        if [ "$label_length" -gt "$size" ]; then
            echob "This value is too large for the $((i+1))-th column!"
            return 1
        fi
        padding=$(($size - $label_length))
        format+="$label$(printf '%*s' "$padding" '')$divider"
    done
    echo "${format%$divider}"
}


#######################################
# Format the header row accordingly to the input width
# Globals:
#   None
# Arguments:
#   $1: array of the sizes
#   $2: array of the names
#   $3: style
# Outputs:
#   Formatted header row to stdout
# Returns:
#   0 on success
#   1 on different arrays' lengths
#   2 on name not fitting its column's width
#######################################
draw_tabular_header() {
    local -n column_size_array="$1"
    local -n column_name_array="$2"
    local -n style="${3:-TABULAR_STYLE_DEFAULT}"

    if [ "${#column_name_array[@]}" -ne "${#column_size_array[@]}" ]; then
        echob "There should be as many columns' names as sizes"
        return 1
    fi

    for (( i=0; i<${#column_name_array[@]}; i++ )); do
        if [ "${#column_name_array[i]}" -gt "${column_size_array[i]}" ]; then
            echob "The column's name should fit in the column"
            return 2
        fi
    done

    _get_row_format column_size_array column_name_array "${style[VRTCL_DIVIDER]}"
    local separator_row_fields=( $(_repeat_thrut_cols column_size_array "${style[HRZTL_DIVIDER]}") )
    _get_row_format column_size_array separator_row_fields "${style[INTER_DIVIDER]}"
}


#######################################
# Format an entry accordingly to the input width
# Globals:
#   None
# Arguments:
#   $1: array of the sizes
#   $2: array of the values
#   $3: style
# Outputs:
#   Formatted entry row to stdout
# Returns:
#   0 on success
#   1 on different arrays' lengths
#######################################
draw_tabular_row() {
    local -n column_size_array=$1
    local -n value_array=$2
    local -n style="${3:-TABULAR_STYLE_DEFAULT}"

    if [ "${#value_array[@]}" -ne "${#column_size_array[@]}" ]; then
        echob "There should be as many columns' values as sizes"
        return 1
    fi

    _get_row_format column_size_array value_array "${style[VRTCL_DIVIDER]}"
}
