let nicknamesHistoryButton = document.querySelector('.nickname-inline');
let isHistoryHidden = true;

nicknamesHistoryButton.addEventListener("click",function(event){
    if(isHistoryHidden){
        document.querySelector('.nicknames-history').style.opacity = '0.85';
        document.querySelector('.nicknames-history').style.visibility = 'visible';
        document.querySelector('.profile-triangle').style.transform = 'rotate(180deg)';
        isHistoryHidden = false;
    } else {
        document.querySelector('.nicknames-history').style.opacity = '0';
        document.querySelector('.nicknames-history').style.visibility = 'hidden';
        document.querySelector('.profile-triangle').style.transform = 'rotate(0deg)';
        isHistoryHidden = true;
    }
});