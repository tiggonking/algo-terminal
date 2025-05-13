
###################################################
##### SETTING OPERATING SYSTEM #####
###################################################

# This is an official python image.
# It uses debian bookworm/debian 12 (latest debian version)
# Debian has much smaller image sizes compared to ubuntu.
# And VScode suggest using ubuntu or debian based images for compatibility.
# also check https://github.com/docker-library/python/blob/master/3.12/slim-bookworm/Dockerfile
FROM python:3.13.3-slim-bookworm

# General settings
USER root
ENV DEBIAN_FRONTEND=noninteractive

###################################################
##### OS LEVEL CONFIGURATIONS #####
###################################################

# set up a dir for our stuff
RUN mkdir -p /algoterminal
RUN chmod -R 777 /algoterminal

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    cmake \
    wget \
    zsh \
    openssh-client \
    jq \
    unzip

###################################################
##### SETTING UP ZSH WITH CUSTOM SHELL PROMPT #####
###################################################

# configure better shell stuff with oh my zsh, some plugins and a improved history search with atuin
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
RUN git clone https://github.com/zsh-users/zsh-autosuggestions.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
RUN git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
RUN git clone https://github.com/zdharma-continuum/fast-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/fast-syntax-highlighting
RUN git clone --depth 1 -- https://github.com/marlonrichert/zsh-autocomplete.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autocomplete
#replace theme line in zshrc to not use the standard oh my zsh theme. Starship.rs >>>>> oh my zsh themes
RUN sed -i 's/^ZSH_THEME=".*"/ZSH_THEME=""/' ~/.zshrc
# set plugins line to plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)
RUN sed -i 's/^plugins=(.*)/plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)/' ~/.zshrc
# Next, set up awesome shell history with atuin
RUN bash -c 'bash <(curl -sSL https://raw.githubusercontent.com/atuinsh/atuin/main/install.sh)'

# The following will persist shell history between sessions
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && echo "$SNIPPET" >> "/root/.bashrc"

# Same for Zsh history
RUN SNIPPET="export HISTFILE=/commandhistory/.zsh_history; setopt INC_APPEND_HISTORY" \
    && echo "$SNIPPET" >> "/root/.zshrc"

###################################################
##### CONFIGURING PYTHON AND INIT SCRIPTS #####
###################################################

# Set up an installation env
COPY ./requirements.txt /init/requirements.txt

# Install non-ib python packages
RUN pip install uv
RUN uv pip install -r /init/requirements.txt --system


###################################################
##### Extra niceties #####
###################################################
# Install starship for zsh
RUN curl -fsSL https://starship.rs/install.sh | sh -s -- -y

# Copy configuration for starship into the container
RUN mkdir -p /root/.config

COPY ./starship.toml /root/.config/starship.toml

# Add starship eval to zshrc
RUN echo 'eval "$(starship init zsh)"' >> /root/.zshrc