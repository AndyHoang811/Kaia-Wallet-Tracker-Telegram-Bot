import os
import telebot
import requests
import sqlite3
import threading
import time
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables from a .env file
load_dotenv()

# Get tokens from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
KAIASCAN_API_TOKEN = os.getenv('KAIASCAN_API_TOKEN')

# Initialize the Telegram bot
bot = telebot.TeleBot(BOT_TOKEN)

def init_database():
    """Initialize SQLite database for tracking addresses"""
    conn = sqlite3.connect('tracked_addresses.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracked_addresses (
            user_id INTEGER,
            address TEXT,
            label TEXT,
            last_transaction_hash TEXT,
            last_transaction_time TEXT,
            PRIMARY KEY (user_id, address)
        )
    ''')
    conn.commit()
    return conn, cursor

DB_CONN, DB_CURSOR = init_database()

def parse_transaction_details(transaction, label=None):
    """
    Parse and format transaction details for user-friendly display
    
    :param transaction: Transaction dictionary from API response
    :param label: Optional label of the tracked wallet
    :return: Formatted transaction message
    """
    # Parse datetime
    tx_time = datetime.fromisoformat(transaction['datetime'].replace('Z', '+00:00'))
    formatted_time = tx_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Extract transaction details
    tx_hash = transaction['transaction_hash']
    from_address = transaction['from']
    to_address = transaction['to']
    tx_type = transaction.get('transaction_type', 'Unknown')
    amount = transaction.get('amount', '0')
    tx_fee = transaction.get('transaction_fee', '0')
    method_signature = transaction.get('signature', 'N/A')
    
    # Construct detailed message with optional wallet label
    message_parts = [f"""🚨 [New Transaction Detected] 🚨"""]
    
    # Add wallet label if provided
    if label:
        message_parts.append(f"📍 Wallet: {label}")
    
    # Continue with rest of the message
    message_parts.extend([
        f"""
📅 Time: {formatted_time}
🔗 Transaction Hash: {tx_hash}
📤 From: {from_address}
📥 To: {to_address}

Details:
- Type: {tx_type}
- Amount: {amount} KAIA
- Transaction Fee: {tx_fee} KAIA
- Method: {method_signature}

Kaiascan Link: https://kaiascan.io/tx/{tx_hash}
"""])
    
    return "\n".join(message_parts), tx_hash
    
def add_tracked_address(user_id, address, label=None):
    """Add an address to be tracked by a user with an optional label"""
    try:
        # First, get the latest transaction to set as initial reference
        url = f'https://mainnet-oapi.kaiascan.io/api/v1/accounts/{address}/transactions?page=1&size=1'
        headers = {
            'Accept': '*/*',
            'Authorization': f'Bearer {KAIASCAN_API_TOKEN}'
        }
        
        response = requests.get(url, headers=headers)
        
        # If no transactions found, use a placeholder
        last_hash = 'NO_TRANSACTIONS'
        last_time = datetime.now(timezone.utc).isoformat()
        
        if response.status_code == 200:
            data = response.json()
            if data['results']:
                last_hash = data['results'][0]['transaction_hash']
                last_time = data['results'][0]['datetime']
        
        # Use label if provided, otherwise set to address
        if not label:
            label = address
        
        # Insert or replace the tracked address
        DB_CURSOR.execute('''
            INSERT OR REPLACE INTO tracked_addresses 
            (user_id, address, label, last_transaction_hash, last_transaction_time) 
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, address, label, last_hash, last_time))
        DB_CONN.commit()
        return True
    except Exception as e:
        print(f"Error tracking address: {e}")
        return False
        

def list_tracked_addresses(user_id):
    """List all tracked addresses for a user"""
    try:
        DB_CURSOR.execute('''
            SELECT address, label FROM tracked_addresses 
            WHERE user_id = ?
        ''', (user_id,))
        return DB_CURSOR.fetchall()
    except Exception as e:
        print(f"Error listing tracked addresses: {e}")
        return []

def remove_tracked_address(user_id, identifier):
    """Remove a tracked address for a user by address or label"""
    try:
        # First, try to remove by exact address match
        DB_CURSOR.execute('''
            DELETE FROM tracked_addresses 
            WHERE user_id = ? AND (address = ? OR label = ?)
        ''', (user_id, identifier, identifier))
        rows_affected = DB_CURSOR.rowcount
        DB_CONN.commit()
        
        return rows_affected > 0
    except Exception as e:
        print(f"Error removing tracked address: {e}")
        return False

def get_latest_transaction(address):
    """Fetch the latest transaction hash for an address"""
    try:
        url = f'https://mainnet-oapi.kaiascan.io/api/v1/accounts/{address}/transactions?page=1&size=1'
        headers = {
            'Accept': '*/*',
            'Authorization': f'Bearer {KAIASCAN_API_TOKEN}'
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data['results']:
                return data['results'][0]['transaction_hash']
        return None
    except Exception as e:
        print(f"Error fetching latest transaction: {e}")
        return None
        
def check_new_transactions():
    """Periodically check for new transactions for tracked addresses"""
    while True:
        try:
            # Fetch all tracked addresses
            DB_CURSOR.execute('SELECT DISTINCT user_id, address, label, last_transaction_hash, last_transaction_time FROM tracked_addresses')
            tracked = DB_CURSOR.fetchall()
            
            for user_id, address, label, last_hash, last_time in tracked:
                try:
                    # Get transactions since the last known transaction
                    url = f'https://mainnet-oapi.kaiascan.io/api/v1/accounts/{address}/transactions?page=1&size=20'
                    headers = {
                        'Accept': '*/*',
                        'Authorization': f'Bearer {KAIASCAN_API_TOKEN}'
                    }
                    
                    response = requests.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        transactions = data['results']
                        
                        # Filter transactions after the last known transaction
                        new_transactions = [
                            tx for tx in transactions 
                            if tx['transaction_hash'] != last_hash and 
                            datetime.fromisoformat(tx['datetime'].replace('Z', '+00:00')) > 
                            datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                        ]
                        
                        # Sort transactions by time to process in chronological order
                        new_transactions.sort(key=lambda x: x['datetime'])
                        
                        # Process each new transaction
                        for tx in new_transactions:
                            try:
                                # Format transaction message - NOTE THE LABEL PASSED HERE
                                message, latest_hash = parse_transaction_details(tx, label)
                                
                                # Send notification
                                bot.send_message(user_id, message)
                                
                                # Update last transaction details
                                DB_CURSOR.execute('''
                                    UPDATE tracked_addresses 
                                    SET last_transaction_hash = ?, 
                                        last_transaction_time = ? 
                                    WHERE user_id = ? AND address = ?
                                ''', (latest_hash, tx['datetime'], user_id, address))
                                DB_CONN.commit()
                            
                            except Exception as tx_error:
                                print(f"Error processing transaction for {address}: {tx_error}")
                
                except Exception as address_error:
                    print(f"Error checking transactions for {address}: {address_error}")
            
            # Wait for 2 minutes before next check to avoid overwhelming the API
            time.sleep(30)
        
        except Exception as e:
            print(f"Error in transaction checking loop: {e}")
            time.sleep(10)
            

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

# Command handler for /track
@bot.message_handler(commands=['track'])
def handle_track(message):
    try:
        # Split the message to get the address and optional label
        parts = message.text.split(maxsplit=2)
        
        if len(parts) < 2:
            bot.reply_to(message, "❌ Please use the format: /track 0x... [Optional Label]")
            return
        
        address = parts[1]
        label = parts[2] if len(parts) > 2 else None
        
        # Validate basic address format
        if not address.startswith('0x') or len(address) != 42:
            bot.reply_to(message, "❌ Invalid wallet address. Please provide a valid 0x... address.")
            return
        
        # Add to tracked addresses
        if add_tracked_address(message.from_user.id, address, label):
            # Prepare confirmation message with label info
            label_info = f" with label '{label}'" if label else ""
            bot.reply_to(message, f"✅ Address {address}{label_info} is now being tracked. You'll receive notifications for new transactions.")
        else:
            bot.reply_to(message, "❌ Failed to track the address. Please try again.")
    
    except Exception as e:
        bot.reply_to(message, "❌ An error occurred. Please try again.")
        print(f"Error in track command: {e}")

# Command handler for /list
@bot.message_handler(commands=['list'])
def handle_list_tracked(message):
    try:
        tracked_addresses = list_tracked_addresses(message.from_user.id)
        
        if not tracked_addresses:
            bot.reply_to(message, "🔍 No addresses are currently being tracked.")
            return
        
        # Format the list of tracked addresses
        addresses_list = "\n".join([f"🔗 {addr} (Label: {label})" for addr, label in tracked_addresses])
        response = f"🚀 Your Tracked Addresses:\n{addresses_list}"
        
        bot.reply_to(message, response)
    
    except Exception as e:
        bot.reply_to(message, "❌ An error occurred while listing tracked addresses.")
        print(f"Error in list command: {e}")

# Command handler for /untrack
@bot.message_handler(commands=['untrack'])
def handle_untrack(message):
    try:
        # Split the message to get the identifier (address or label)
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            bot.reply_to(message, "❌ Please use the format: /untrack [Address or Label]")
            return
        
        identifier = parts[1].strip()
        
        # Attempt to remove the tracked address
        if remove_tracked_address(message.from_user.id, identifier):
            bot.reply_to(message, f"✅ Address/Label '{identifier}' is no longer being tracked.")
        else:
            bot.reply_to(message, f"❌ No tracked address found with '{identifier}'.")
    
    except Exception as e:
        bot.reply_to(message, "❌ An error occurred. Please try again.")
        print(f"Error in untrack command: {e}")


# Start command handler
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_message = """
👋 Welcome to Kaia Address Tracker Bot!

Kaia Wallet Tracker bot that allows users to quickly and easily track, monitor, and explore wallet activities effortlessly.

Available Commands:
- /balance 0x... : Check Native balance
- /tokens 0x... : List Token holdings
- /nfts 0x... : List NFT holdings
- /track 0x... : Track an address for transactions
- /list 0x... : List tracked addresses
- /untrack 0x... : Stop tracking an address


"""
    bot.reply_to(message, welcome_message)


# Start the bot
def main():
    # Start transaction checking thread
    tx_thread = threading.Thread(target=check_new_transactions, daemon=True)
    tx_thread.start()
    
    print("Bot is running...")
    bot.polling(none_stop=True)

if __name__ == '__main__':
    main()
