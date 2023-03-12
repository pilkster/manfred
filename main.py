# Importing the required modules
from sendblue import Sendblue
from dotenv import load_dotenv
from flask import Flask, request, redirect
from replit import db
import json
import os
import openai
import tiktoken
import bcrypt

encoding = tiktoken.encoding_for_model('gpt-3.5-turbo')
# Options
context_msgs = 5
max_tokens = 4000
temperature = 0.1
prompt = "You are a helpful assistant."
error_message = "I'm sorry, I'm having trouble responding right now."
moderation_message = "I'm sorry, this content was flagged as inappropriate."
DASHBOARD_PASSWORD = bcrypt.hashpw(b"1234", bcrypt.gensalt()).decode('ascii')

keys = db.keys()
if "context_msgs" not in keys:
    db["context_msgs"] = context_msgs
else:
    context_msgs = db["context_msgs"]

if "max_tokens" not in keys:
    db["max_tokens"] = max_tokens
else:
    max_tokens = db["max_tokens"]

if "temperature" not in keys:
    db["temperature"] = temperature
else:
    temperature = db["temperature"]

if "prompt" not in keys:
    db["prompt"] = prompt
else:
    prompt = db["prompt"]

if "error_message" not in keys:
    db["error_message"] = error_message
else:
    error_message = db["error_message"]

if "moderation_message" not in keys:
    db["moderation_message"] = moderation_message
else:
    moderation_message = db["moderation_message"]

if "DASHBOARD_PASSWORD" not in keys:
    db["DASHBOARD_PASSWORD"] = DASHBOARD_PASSWORD
else:
    DASHBOARD_PASSWORD = db["DASHBOARD_PASSWORD"]


# Loading the environment variables from a .env file
load_dotenv()

# Getting the API key and secret from the environment variables
SENDBLUE_API_KEY = os.environ.get("SENDBLUE_API_KEY")
SENDBLUE_API_SECRET = os.environ.get("SENDBLUE_API_SECRET")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Checking if the API key and secret are set
if not SENDBLUE_API_KEY:
    raise ValueError("SENDBLUE_API_KEY is not set")
if not SENDBLUE_API_SECRET:
    raise ValueError("SENDBLUE_API_SECRET is not set")
if not WEBHOOK_SECRET:
    raise ValueError("WEBHOOK_SECRET is not set")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set")
if not DASHBOARD_PASSWORD:
    raise ValueError("DASHBOARD_PASSWORD is not set")


openai.api_key = OPENAI_API_KEY

# Creating a Sendblue object
sendblue = Sendblue(SENDBLUE_API_KEY, SENDBLUE_API_SECRET)

# Creating a Flask application instance
app = Flask(__name__)

# Defining routes on the server
@app.route('/webhook', methods=['POST'])
def webhook():
    global context_msgs
    global max_tokens
    global temperature
    global prompt
    global error_message
    global moderation_message
    # Reading the JSON request body
    json_body = request.get_json()
    if json_body['status'] != 'RECEIVED':
      print("Received Error:")
      print(json_body)
      return 'Received some error'
    else:
        number = json_body['number'][1:]
        message = json_body['content']
        db_keys = db.keys()

        if "convo"+number not in db_keys:
            db["convo"+number] = '{"content": []}'

        # Make sure the text is not bigger than the max token, do -10 because we need at least 10 tokens for the response.
        if len(encoding.encode(message)) > max_tokens - 10:
          return sendblue.send_message("+"+number, {
              'content': "Your text is too large!"
          })

        prevConvo = db["convo"+number]
        prevConvo = json.loads(prevConvo)
        prevConvo["content"].append({'role': 'user', 'content': message})
        db["convo"+number] = json.dumps(prevConvo)

        sendContent = prevConvo["content"]

        if len(sendContent) > context_msgs:
            sendContent = sendContent[-context_msgs:]

        # Push system message to first of array
        sendContent.insert(0, {'role': 'system', 'content': prompt})

        # Make sure the chat history is not too big
        sum = 0
        for c in sendContent:
          # Measuring each message's token
          sum += len(encoding.encode(c['content']))
        while (sum > (max_tokens-10)) and len(sendContent) > 1:
          # If the total is above max token, we remove the oldest message. Index 1 because we don't want to remove the initial system prompt message
          sendContent.pop(1)
          for c in sendContent:
            # Recalculate the sum
            sum += len(encoding.encode(c['content']))

        if(len(sendContent) <= 1):
          return sendblue.send_message("+"+number, {
              'content': "Your text is too large!"
          })


        try:
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=sendContent,
                max_tokens=max_tokens-sum,
                temperature=temperature,
            )

            response = completion.choices[0].message.content

            modResponse = openai.Moderation.create(
                input=response
            )
            flagged = modResponse["results"][0]["flagged"]

            if flagged:
                response = moderation_message

            prevConvo["content"].append({'role': 'assistant', 'content': response})
            db["convo"+number] = json.dumps(prevConvo)

            sendblue.send_message("+"+number, {
              'content': response
            })
        except Exception as e:
            print(e)
            sendblue.send_message("+"+number, {
              'content': error_message
            })
            prevConvo["content"].append({'role': 'assistant', 'content': error_message})
            db["convo"+number] = json.dumps(prevConvo)
    return 'JSON received'

@app.route('/', methods=['GET'])
def index():
    # Send dashboard.html file
    return app.send_static_file('dashboard.html')

@app.route('/verify_password', methods=['POST'])
def verify_password():
    global DASHBOARD_PASSWORD
    # Read password from request
    try:
        json_password = request.get_json()['password']

        if bcrypt.checkpw(bytes(json_password, 'utf-8'), bytes(DASHBOARD_PASSWORD, 'utf-8')):
            return 'true'
        else:
            return 'false'
    except:
        return 'false'

@app.route('/update_options', methods=['POST'])
def update_options():
    global context_msgs
    global max_tokens
    global temperature
    global prompt
    global error_message
    global moderation_message
    # Read options from request form
    try:
      newcontext_msgs = int(request.form['context_msgs'])
      newmax_tokens = int(request.form['max_tokens'])
      newtemperature = float(request.form['temperature'])
      newprompt = request.form['prompt']
      newerror_message = request.form['error_message']
      newmoderation_message = request.form['moderation_message']
      password = request.form['password']

      if bcrypt.checkpw(bytes(password, 'utf-8'), bytes(DASHBOARD_PASSWORD, 'utf-8')) == False:
        return 'Incorrect Password'

      db["context_msgs"] = newcontext_msgs
      context_msgs = newcontext_msgs

      db["max_tokens"] = newmax_tokens
      max_tokens = newmax_tokens

      db["temperature"] = newtemperature
      temperature = newtemperature

      db["prompt"] = newprompt
      prompt = newprompt

      db["error_message"] = newerror_message
      error_message = newerror_message

      db["moderation_message"] = newmoderation_message
      moderation_message = newmoderation_message

      # Redirect to dashboard
      return redirect('/?success=true')
    except Exception as e:
        print("Failed to update options")
        print(e)
        return 'Something went wrong while updating'

@app.route('/get_all_messages', methods=['GET'])
def get_messages():
    global db
    try:
        password = request.args.get('password')

        if not bcrypt.checkpw(bytes(password, 'utf-8'), bytes(DASHBOARD_PASSWORD, 'utf-8')):
            return 'Incorrect password'

        convolist = db.prefix("convo")
        output = []
        # Create a JSON array of all messages and their number
        for key in convolist:
            value = db[key]
            data = json.loads(value)
            data["number"] = key[5:]
            output.append(data)

        return json.dumps(output)
    except:
        return 'Something went wrong while getting messages'


@app.route('/get_options', methods=['GET'])
def get_options():
    global context_msgs
    global max_tokens
    global temperature
    global prompt
    global error_message
    global moderation_message
    # Read options from request form
    try:
        password = request.args.get('password')

        if not bcrypt.checkpw(bytes(password, 'utf-8'), bytes(DASHBOARD_PASSWORD, 'utf-8')):
            return 'Incorrect password'

        return json.dumps({
            "context_msgs": context_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "prompt": prompt,
            "error_message": error_message,
            "moderation_message": moderation_message
        })
    except:
        return 'Something went wrong while getting options'

@app.route('/change_password', methods=['GET'])
def change_password():
    global DASHBOARD_PASSWORD
    # try:
    password = request.args.get('password')
    newPass = request.args.get('newPass')

    if(not password or not newPass):
      return 'Missing fields'

    print(DASHBOARD_PASSWORD, password)
    if not bcrypt.checkpw(bytes(password, 'utf-8'), bytes(DASHBOARD_PASSWORD, 'utf-8')):
      return 'Incorrect password'

    hashed = bcrypt.hashpw(bytes(newPass, 'utf-8'), bcrypt.gensalt())

    DASHBOARD_PASSWORD = hashed.decode('ascii')
    db["DASHBOARD_PASSWORD"] = hashed.decode('ascii')
    
    
    return "Success"
    # except:
    #     return 'Something went wrong while setting password'


if __name__ == '__main__':
    # Running the Flask app
    app.run(debug=True, host='0.0.0.0')
