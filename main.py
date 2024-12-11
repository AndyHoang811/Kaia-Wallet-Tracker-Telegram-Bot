import os
import telebot
import requests
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Get tokens from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
KAIASCAN_API_TOKEN = os.getenv('KAIASCAN_API_TOKEN')

# Initialize the Telegram bot
bot = telebot.TeleBot(BOT_TOKEN)

def get_address_balance(address):
    """
    Retrieve wallet native balance from Kaiascan API
    
    :param address: Wallet address to check
    :return: Balance information or error message
    """
    try:
        balance_url = f'https://mainnet-oapi.kaiascan.io/api/v1/accounts/{address}'
        headers = {
            'Accept': '*/*',
            'Authorization': f'Bearer {KAIASCAN_API_TOKEN}'
        }
        
        # Make the API request
        balance_response = requests.get(balance_url, headers=headers)
        kaia_price_url = 'https://mainnet-oapi.kaiascan.io/api/v1/kaia'
        kaia_price_response = requests.get(kaia_price_url, headers=headers)
        
        # Check if the request was successful
        if balance_response.status_code == 200:
            balance_data = balance_response.json()
            kaia_price_data = kaia_price_response.json()
            kaia_balance = float(balance_data['balance'])
            usd_price = float(kaia_price_data['klay_price']['usd_price'])

            # Calculate Kaia value in USD
            kaia_value_usd = kaia_balance * usd_price
            return f"""
🏦 [ADDRESS BALANCE] 🏦

Address: {balance_data['address']}
Balance: {balance_data['balance']} KAIA ( ${kaia_value_usd:.2f} USD )
"""
        else:
            return f"❌ Error: Unable to fetch balance. Status code: {response.status_code}"
    
    except requests.RequestException as e:
        return f"❌ Network Error: {str(e)}"
    except KeyError:
        return "❌ Error: Unexpected API response format"
    except Exception as e:
        return f"❌ Unexpected Error: {str(e)}"

def get_address_tokens(address):
    """
    Retrieve wallet token balances from Kaiascan API
    
    :param address: Wallet address to check
    :return: Token balance information or error message
    """
    try:
        url = f'https://mainnet-oapi.kaiascan.io/api/v1/accounts/{address}/token-details?size=2000'
        headers = {
            'Accept': '*/*',
            'Authorization': f'Bearer {KAIASCAN_API_TOKEN}'
        }
        
        # Make the API request
        response = requests.get(url, headers=headers)
        
        # Check if the request was successful
        if response.status_code == 200:
            data = response.json()
            
            # If no tokens found
            if not data['results']:
                return "🔍 No tokens found for this wallet."
            
            # Prepare simplified token balance message
            token_details = []
            for token in data['results']:
                contract = token['contract']
                token_details.append(f"- {contract['name']}: {token['balance']} {contract['symbol']}")
            
            # Combine all token details
            return "💰 [TOKEN HOLDINGS] 💰\n\n Address: "+ address + "\n\n" + "\n".join(token_details)
        
        else:
            return f"❌ Error: Unable to fetch token details. Status code: {response.status_code}"
    
    except requests.RequestException as e:
        return f"❌ Network Error: {str(e)}"
    except KeyError:
        return "❌ Error: Unexpected API response format"
    except Exception as e:
        return f"❌ Unexpected Error: {str(e)}"

def get_address_nfts(address):
    """
    Retrieve wallet NFT balances from Kaiascan API
    
    :param address: Wallet address to check
    :return: NFT balance information or error message
    """
    try:
        # Fetch KIP17 NFTs
        kip17_url = f'https://mainnet-oapi.kaiascan.io/api/v1/accounts/{address}/nft-balances/kip17'
        
        # Fetch KIP37 NFTs
        kip37_url = f'https://mainnet-oapi.kaiascan.io/api/v1/accounts/{address}/nft-balances/kip37'
        
        headers = {
            'Accept': '*/*',
            'Authorization': f'Bearer {KAIASCAN_API_TOKEN}'
        }
        
        # Make API requests
        kip17_response = requests.get(kip17_url, headers=headers)
        kip37_response = requests.get(kip37_url, headers=headers)
        
        # Check if requests were successful
        if kip17_response.status_code != 200 or kip37_response.status_code != 200:
            return f"❌ Error: Unable to fetch NFT details. KIP17 Status: {kip17_response.status_code}, KIP37 Status: {kip37_response.status_code}"
        
        kip17_data = kip17_response.json()
        kip37_data = kip37_response.json()
        
        # Group NFTs by contract type
        nft_groups = {
            'KIP17': [],
            'ERC1155': []
        }
        
        # Process KIP17 NFTs
        for nft_contract in kip17_data['results']:
            contract_address = nft_contract['contract']['contract_address']
            contract_type = nft_contract['contract']['contract_type']
            
            # Get NFT contract info
            contract_url = f'https://mainnet-oapi.kaiascan.io/api/v1/nfts/{contract_address}'
            contract_response = requests.get(contract_url, headers=headers)
            
            if contract_response.status_code == 200:
                contract_info = contract_response.json()
                nft_groups['KIP17'].append({
                    'name': contract_info['name'],
                    'count': nft_contract['token_count'],
                    'symbol': contract_info['symbol']
                })
        
        # Process KIP37/ERC1155 NFTs
        for nft_contract in kip37_data['results']:
            contract_address = nft_contract['contract']['contract_address']
            contract_type = nft_contract['contract']['contract_type']
            # Get NFT contract info
            contract_url = f'https://mainnet-oapi.kaiascan.io/api/v1/nfts/{contract_address}'
            contract_response = requests.get(contract_url, headers=headers)
            
            if contract_response.status_code == 200:
                contract_info = contract_response.json()
                nft_groups['ERC1155'].append({
                    'name': contract_info['name'],
                    'count': nft_contract['token_count'],
                    'tokenid': nft_contract['token_id'],
                    'symbol': contract_info['symbol']
                })
        
        # If no NFTs found
        if not any(nft_groups.values()):
            return "🔍 No NFTs found for this address."
        
        # Format the output
        output = ["🖼️ [NFT HOLDINGS] 🖼️\n\nAddress: "+ address]
        
        # KIP17 NFTs
        if nft_groups['KIP17']:
            output.append("\n[KIP17]")
            # Sort KIP17 NFTs by token count in descending order
            kip17_sorted = sorted(nft_groups['KIP17'], key=lambda x: x['count'], reverse=True)
            for nft in kip17_sorted:
                output.append(f"- {nft['name']}: {nft['count']} ")
        
        # ERC1155 NFTs
        if nft_groups['ERC1155']:
            output.append("\n[ERC1155]")
            # Sort ERC1155 NFTs by token count in descending order
            erc1155_sorted = sorted(nft_groups['ERC1155'], key=lambda x: x['count'], reverse=True)
            for nft in erc1155_sorted:
                output.append(f"- {nft['name']}: {nft['count']} ({nft['tokenid']})")
        
        # Combine and return output
        return "\n".join(output)
    
    except requests.RequestException as e:
        return f"❌ Network Error: {str(e)}"
    except KeyError:
        return "❌ Error: Unexpected API response format"
    except Exception as e:
        return f"❌ Unexpected Error: {str(e)}"


# Command handler for /balance
@bot.message_handler(commands=['balance'])
def handle_balance(message):
    # Check if the user provided an address
    try:
        # Split the message to get the address (expecting /balance 0x...)
        _, address = message.text.split(maxsplit=1)
        
        # Validate basic address format
        if not address.startswith('0x') or len(address) != 42:
            bot.reply_to(message, "❌ Invalid wallet address. Please provide a valid 0x... address.")
            return
        
        # Get and send balance information
        balance_info = get_address_balance(address)
        bot.reply_to(message, balance_info)
    
    except ValueError:
        bot.reply_to(message, "❌ Please use the format: /balance 0x...")

# Command handler for /tokens
@bot.message_handler(commands=['tokens'])
def handle_tokens(message):
    # Check if the user provided an address
    try:
        # Split the message to get the address (expecting /tokens 0x...)
        _, address = message.text.split(maxsplit=1)
        
        # Validate basic address format
        if not address.startswith('0x') or len(address) != 42:
            bot.reply_to(message, "❌ Invalid wallet address. Please provide a valid 0x... address.")
            return
        
        # Get and send token balance information
        token_info = get_address_tokens(address)
        bot.reply_to(message, token_info)
    
    except ValueError:
        bot.reply_to(message, "❌ Please use the format: /tokens 0x...")

# Command handler for /nfts
@bot.message_handler(commands=['nfts'])
def handle_nfts(message):
    # Check if the user provided an address
    try:
        # Split the message to get the address (expecting /nfts 0x...)
        _, address = message.text.split(maxsplit=1)
        
        # Validate basic address format
        if not address.startswith('0x') or len(address) != 42:
            bot.reply_to(message, "❌ Invalid wallet address. Please provide a valid 0x... address.")
            return
        
        # Get and send NFT balance information
        nft_info = get_address_nfts(address)
        bot.reply_to(message, nft_info)
    
    except ValueError:
        bot.reply_to(message, "❌ Please use the format: /nfts 0x...")


# Start command handler
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_message = """
👋 Welcome to Kaia Address Viewer Bot!
Available Commands:
- /balance 0x... : Check Native balance
- /tokens 0x... : List Token holdings
- /nfts 0x... : List NFT holdings

Example:
/balance 0x5eda3f9ab84dc831aa3c811af73f54c4ca9ec5aa
/tokens 0x5eda3f9ab84dc831aa3c811af73f54c4ca9ec5aa
/nfts 0x5eda3f9ab84dc831aa3c811af73f54c4ca9ec5aa
"""
    bot.reply_to(message, welcome_message)

# Start the bot
def main():
    print("Bot is running...")
    bot.polling(none_stop=True)

if __name__ == '__main__':
    main()